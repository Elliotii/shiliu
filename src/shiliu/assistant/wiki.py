from __future__ import annotations

import hashlib
import json
import re
import uuid
from contextlib import contextmanager
from psycopg.types.json import Jsonb
from shiliu.storage.dto import row_dto
from shiliu.storage.scheduler import guard_job, job_transition
from shiliu.assistant.pg_access import PgAssistantAccess
from datetime import datetime
from typing import Any, Callable, Protocol

from shiliu.assistant.snapshots import CapturedSource, SourceChangedDuringCapture
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.memory_policy import anchored_validity, has_time_reference
from shiliu.assistant.sources import CollectionSourceService, SourceScope
from shiliu.assistant.runtime_contract import AssistantConflict, ModelBudgetWait
from shiliu.db import Database, utc_now


class StructuredProvider(Protocol):
    def generate_json(
        self, *, system: str, prompt: str, max_tokens: int = 2400
    ) -> dict[str, Any]: ...


class MaintenanceBudgetExceeded(RuntimeError):
    code = "maintenance_budget_exhausted"


class MaintenanceYield(RuntimeError):
    code = "maintenance_user_returned"


class _StoredResponseProvider:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response

    def generate_json(
        self, *, system: str, prompt: str, max_tokens: int = 2400
    ) -> dict[str, Any]:
        return self.response


class ModelOutcomeUnknown(AssistantConflict):
    code = "external_model_result_unknown"


class BudgetedStructuredProvider:
    def __init__(
        self,
        store,
        batch_id,
        delegate,
        *,
        daily_limit=60,
        continue_allowed=None,
        job=None,
    ):
        self.store = (
            store if isinstance(store, PgAssistantAccess) else PgAssistantAccess(store)
        )
        self.db = self.store.db
        self.batch_id = batch_id
        self.delegate = delegate
        self.daily_limit = daily_limit
        self.continue_allowed = continue_allowed
        self.job = job

    def generate_json(self, *, system, prompt, max_tokens=2400):
        from shiliu.storage.budget import reserve_dispatch, settle_dispatch
        from shiliu.storage.fences import CoordinationConflict

        if self.continue_allowed:
            self.continue_allowed()
        request_hash = hashlib.sha256(
            json.dumps(
                [system, prompt, max_tokens], ensure_ascii=False, separators=(",", ":")
            ).encode()
        ).hexdigest()
        dispatch_id = (
            "wiki:"
            + hashlib.sha256(
                json.dumps(
                    [
                        self.db.workspace_id,
                        self.store.principal_id,
                        self.job["id"] if self.job else self.batch_id,
                        request_hash,
                    ],
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
        )
        with self.db.connect(guard=True) as c:
            if self.job:
                guard_job(
                    c,
                    self.db.context,
                    self.job["id"],
                    self.job["lease_owner"],
                    self.job["lease_epoch"],
                )
            # Integration has one model response per Job. A changed page/basis
            # cannot turn an unpersisted prior response into permission to resend.
            if (
                self.job
                and self.job.get("kind") == "wiki_integrate"
                and c.execute(
                    "SELECT 1 FROM model_dispatch_receipts WHERE workspace_id=%s AND principal_id=%s AND job_id=%s",
                    (self.db.workspace_id, self.store.principal_id, self.job["id"]),
                ).fetchone()
            ):
                raise ModelOutcomeUnknown(
                    "wiki_integration_dispatched_without_matching_staged_result"
                )
            old = c.execute(
                "SELECT status FROM model_dispatch_receipts WHERE workspace_id=%s AND principal_id=%s AND dispatch_id=%s",
                (self.db.workspace_id, self.store.principal_id, dispatch_id),
            ).fetchone()
            if old:
                raise ModelOutcomeUnknown(
                    "wiki_model_result_already_dispatched_use_staged_proposal"
                )
            if self.batch_id:
                row = c.execute(
                    "SELECT * FROM assistant_maintenance_batches WHERE workspace_id=%s AND id=%s FOR UPDATE",
                    (self.db.workspace_id, self.batch_id),
                ).fetchone()
                if row is None or row["calls_used"] >= row["model_limit"]:
                    raise MaintenanceBudgetExceeded("本批后台模型请求预算已耗尽")
            try:
                reserve_dispatch(
                    c,
                    self.db.context,
                    dispatch_id,
                    lane="background",
                    request_limit=self.daily_limit,
                    request_hash=request_hash,
                    job_id=self.job["id"] if self.job else None,
                )
            except CoordinationConflict as exc:
                if str(exc) == "budget_exhausted":
                    raise ModelBudgetWait("后台模型每日额度已用完") from exc
                raise
            if self.batch_id:
                c.execute(
                    "UPDATE assistant_maintenance_batches SET calls_used=calls_used+1 WHERE workspace_id=%s AND id=%s",
                    (self.db.workspace_id, self.batch_id),
                )
        # External result can be unknown. The immutable dispatch identity prevents
        # automatic replay; a persisted staged proposal is the recovery source.
        try:
            return self.delegate.generate_json(
                system=system, prompt=prompt, max_tokens=max_tokens
            )
        finally:
            with self.db.connect() as c:
                settle_dispatch(c, self.db.context, dispatch_id, usage=None)


class WikiService:
    EXTRACTION_VERSION = "source-card-v2"
    COMPILER_VERSION = "wiki-compiler-v7"

    @staticmethod
    def _reference_like(value: str) -> bool:
        """Only label a named work or document as a cited source, never gear."""
        return bool(
            re.search(
                r"论文|文档|报告|文章|书籍|指南|白皮书|标准|规范|研究|官网|官方原文|"
                r"\b(?:paper|study|report|documentation|guide|specification)\b",
                value,
                re.IGNORECASE,
            )
            or len(re.findall(r"[A-Za-z]{3,}", value)) >= 5
        )

    def __init__(
        self,
        *,
        db: Database,
        store: PgAssistantAccess,
        sources: CollectionSourceService,
        principal_id: str = "local_operator",
    ) -> None:
        self.db = db
        self.store = store
        self.sources = sources
        self.principal_id = principal_id
        self.workspace_id = db.context.workspace_id
        if principal_id != db.context.user_id:
            raise ValueError("principal_context_mismatch")
        self.retrieval = None
        self.publish_allowed: Callable[[], bool] | None = None
        self.publish_transaction_guard: Callable[[Any], None] | None = None

    def _notify_plan(self, c, plan, *, effects=None, previous=None):
        from shiliu.assistant.notifications import plan_record

        return plan_record(
            c, self.db.context, plan, effect_refs=effects, previous=previous
        )

    def _notify_proposal(self, c, proposal, *, effects=None):
        from shiliu.assistant.notifications import proposal_record

        return proposal_record(c, self.db.context, proposal, effect_refs=effects)

    def _preserve_notification_plan(self, c, plan, new_payload):
        from shiliu.assistant.notifications import plan_fingerprint, message_id

        fingerprint = plan_fingerprint(plan)
        if fingerprint == plan_fingerprint({**plan, "payload": new_payload}):
            return
        if not fingerprint:
            return
        identity = message_id(self.db.context, f"plan:{plan['id']}:{fingerprint}")
        # This candidate is still present now. Preserve only if no full existing
        # receipt proves it and a pending/indexed item will lose its payload.
        referenced = c.execute(
            "SELECT 1 FROM assistant_notifications WHERE workspace_id=%s AND principal_id=%s AND id=%s",
            (self.workspace_id, self.principal_id, identity),
        ).fetchone()
        if not referenced and (
            plan["status"] not in {"pending", "partial"}
            or plan["payload"].get("direct_authorized")
        ):
            return
        receipts = c.execute(
            "SELECT result_json FROM assistant_mutation_receipts WHERE workspace_id=%s AND principal_id=%s AND operation IN ('knowledge_plan_revise','knowledge_plan_replace') AND result_json->>'id'=%s",
            (self.workspace_id, self.principal_id, plan["id"]),
        ).fetchall()
        self._notify_plan(c, plan)
        if any(
            plan_fingerprint(r["result_json"]) == fingerprint
            and r["result_json"].get("results", {}) == plan.get("results", {})
            for r in receipts
        ):
            return
        c.execute(
            "INSERT INTO assistant_mutation_receipts(workspace_id,principal_id,operation_key,operation,result_json,created_at) VALUES(%s,%s,%s,'knowledge_plan_content',%s,%s) ON CONFLICT DO NOTHING",
            (
                self.workspace_id,
                self.principal_id,
                f"plan-content:{plan['id']}:{fingerprint}",
                Jsonb(plan),
                utc_now(),
            ),
        )

    def _record_notification_change(
        self, c, query, parameters, *, cause, plan=None, proposal=None, undo_id=None
    ):
        from shiliu.assistant.notifications import record

        change = dict(c.execute(query + " RETURNING *", parameters).fetchone())
        self._expire_source_patches(c, change["page_id"], exclude=(proposal or {}).get("id"))
        effect = {"type": "wiki_change", "id": str(change["id"])}
        if undo_id:
            c.execute(
                "UPDATE assistant_notifications SET undo_ref=%s,activity_at=clock_timestamp() WHERE workspace_id=%s AND principal_id=%s AND id=%s AND undo_ref IS NULL",
                (cause["operation_key"], self.workspace_id, self.principal_id, undo_id),
            )
        elif plan:
            self._notify_plan(
                c, {**plan, "updated_at": change["created_at"]}, effects=[effect]
            )
        elif proposal:
            self._notify_proposal(
                c, {**proposal, "updated_at": change["created_at"]}, effects=[effect]
            )
        else:
            page = change["after_json"] or change["before_json"]
            record(
                c,
                self.db.context,
                event_key=f"wiki-change:{change['id']}",
                origin_type="wiki_change",
                origin_id=change["id"],
                space_id=page["space_id"],
                source_type="video"
                if cause.get("job_id")
                else "dialogue"
                if cause.get("source_message_ids")
                else "manual",
                cause_refs=cause,
                created_at=change["created_at"],
                read_at=change["created_at"] if change["actor"] == "user" else None,
            )
        return change

    def notification_undo_eligibility(self, c, change, obj):
        if (
            change["operation"] != "discussion_saved"
            or obj["status"] != "active"
            or obj["version"] != change["version"]
        ):
            raise AssistantConflict("wiki_effect_changed_or_not_discussion_save")
        state = c.execute(
            "SELECT before_json FROM assistant_wiki_operation_states WHERE workspace_id=%s AND page_id=%s AND version=%s",
            (self.workspace_id, obj["id"], change["version"]),
        ).fetchone()
        receipt = c.execute(
            "SELECT 1 FROM assistant_mutation_receipts WHERE workspace_id=%s AND principal_id=%s AND operation='knowledge_save' AND result_json->>'id'=%s AND (result_json->>'version')::bigint=%s",
            (self.workspace_id, self.principal_id, obj["id"], change["version"]),
        ).fetchone()
        if not state or not receipt:
            raise AssistantConflict("wiki_effect_receipt_or_direct_before_missing")
        return {"kind": "undo", "expected_version": change["version"]}

    def undo_notification_change(
        self, identity, change_id, *, expected_version, operation_key
    ):
        with self._transaction(operation_key=operation_key) as c:
            change = c.execute(
                "SELECT ch.* FROM assistant_wiki_changes ch JOIN assistant_wiki_pages p ON (p.workspace_id,p.id)=(ch.workspace_id,ch.page_id) WHERE ch.workspace_id=%s AND p.principal_id=%s AND ch.id=%s",
                (self.workspace_id, self.principal_id, change_id),
            ).fetchone()
            if not change:
                raise KeyError(change_id)
            obj = c.execute(
                "SELECT * FROM assistant_wiki_pages WHERE workspace_id=%s AND id=%s FOR UPDATE",
                (self.workspace_id, change["page_id"]),
            ).fetchone()
            self.notification_undo_eligibility(c, change, obj)
            if expected_version != change["version"]:
                raise AssistantConflict("message_effect_version_conflict")
            if change["before_json"] is None:
                return self.manage_page(
                    obj["id"],
                    space_id=obj["space_id"],
                    action="archive",
                    expected_version=expected_version,
                    operation_key=operation_key,
                    conn=c,
                    _notification_id=identity,
                )
            return self.revert(
                obj["id"],
                target_version=int(change["before_json"]["version"]),
                expected_version=expected_version,
                operation_key=operation_key,
                conn=c,
                _notification_id=identity,
            )

    def _notification_cache(self, c, page_id):
        """Build current evidence without capture/publish. Reads immutable files only."""
        rows = c.execute(
            "SELECT DISTINCT video_id,source_revision FROM assistant_wiki_dependencies WHERE workspace_id=%s AND page_id=%s",
            (self.workspace_id, page_id),
        ).fetchall()
        cache = {"@current": {}}
        for row in rows:
            vid = row["video_id"]
            try:
                state = self.sources.snapshots._state(vid, conn=c)
                current = self.sources.snapshots._build_snapshot(state)
                cache[current["revision"]] = current
                from shiliu.assistant.wiki_projection import WikiProjection

                cache["@current"][vid] = {
                    "revision": current["revision"],
                    "token": WikiProjection._state_token(state),
                }
                old = self.sources.snapshots.load(vid, row["source_revision"])
                cache[row["source_revision"]] = old.snapshot
            except (KeyError, ValueError, OSError, SourceChangedDuringCapture):
                # Explicit invalid evidence prevents stale-head equality from
                # accidentally authorizing old source text.
                cache["@current"][vid] = {"revision": ""}
        return cache

    def notification_change(self, c, change, obj):
        current = self._decode_page(obj)
        if current["status"] != "active":
            return {
                "before": None,
                "after": None,
                "reason": "对象已归档或删除，历史正文不可用",
            }
        cache = self._notification_cache(c, current["id"])
        visible = self._visible_page(current, conn=c, snapshot_cache=cache)
        allowed = {b["stable_id"] for b in visible["blocks"] if not b.get("deleted")}
        space = self.store.get_space(current["space_id"], conn=c)
        videos = set(self.sources.visible_video_ids(self._scope(space), conn=c))

        def source_valid(dep):
            vid = dep["video_id"]
            old = dep["source_revision"]
            if vid not in videos:
                return False
            try:
                actual = self.sources.snapshots._build_snapshot(
                    self.sources.snapshots._state(vid, conn=c)
                )
                cache[actual["revision"]] = actual
                if old not in cache:
                    cache[old] = self.sources.snapshots.load(vid, old).snapshot
                return self._source_dependency_current(
                    video_id=vid,
                    old_revision=old,
                    current_revision=actual["revision"],
                    dependency_kind=dep.get("dependency_kind", "source"),
                    cache=cache,
                    conn=c,
                )
            except (KeyError, ValueError, OSError, AssistantConflict, SourceChangedDuringCapture):
                return False

        def state_before(version):
            row = c.execute(
                "SELECT before_json FROM assistant_wiki_operation_states WHERE workspace_id=%s AND page_id=%s AND version=%s",
                (self.workspace_id, current["id"], version),
            ).fetchone()
            return row["before_json"] if row else None

        before_state = state_before(change["version"])
        after_state = (
            self._operation_state(c, current["id"], conn=c)
            if current["version"] == change["version"]
            else state_before(change["version"] + 1)
        )

        def controlled(page, state):
            if not page:
                return None
            blocks = []
            for block in page.get("blocks", []):
                bid = block.get("stable_id")
                if bid not in allowed or block.get("deleted"):
                    continue
                dependencies = [
                    x for x in (state or {}).get("sources", []) if x["block_id"] == bid
                ]
                personal = [
                    x for x in (state or {}).get("personal", []) if x["block_id"] == bid
                ]
                if (
                    block.get("source_refs") or block.get("role") == "source"
                ) and not dependencies:
                    continue
                if dependencies and not all(source_valid(x) for x in dependencies):
                    continue
                if block.get("memory_id") and not personal:
                    continue
                if any(
                    not self._personal_dependency_current(
                        c,
                        space_id=space["id"],
                        memory_id=x["memory_id"],
                        memory_version=x["memory_version"],
                        source_message_id=x.get("source_message_id"),
                        conn=c,
                    )
                    for x in personal
                ):
                    continue
                blocks.append(block)
            materials = [
                {
                    "video_id": x["video_id"],
                    "source_revision": x["source_revision"],
                    "relation": x.get("relation"),
                    "status": x.get("status"),
                }
                for x in (state or {}).get("materials", [])
                if source_valid(x)
            ]
            return {
                "id": page["id"],
                "version": page["version"],
                "blocks": blocks,
                "materials": materials,
            }

        provenance = []
        for state in (before_state, after_state):
            for dep in (state or {}).get("sources", []):
                if not source_valid(dep):
                    continue
                video = c.execute(
                    "SELECT video_url,published_at FROM videos WHERE workspace_id=%s AND id=%s",
                    (self.workspace_id, dep["video_id"]),
                ).fetchone()
                if video:
                    provenance.append(
                        {
                            "video_id": dep["video_id"],
                            "source_revision": dep["source_revision"],
                            "url": video["video_url"],
                            "published_at": video["published_at"],
                        }
                    )
        return {
            "sources": provenance,
            "before": controlled(change["before_json"], before_state),
            "after": controlled(change["after_json"], after_state),
            "operation": change["operation"],
            "reason": None
            if after_state
            else "部分历史依赖未记录；无法证明的正文不展示",
        }

    def notification_plan(self, c, plan):
        # Original validation runs against read-only current evidence. It may
        # reject missing evidence; it must never capture a new source revision.
        safe_results = {
            k: {
                field: value
                for field, value in outcome.items()
                if field in {"status", "page_id", "version"}
            }
            for k, outcome in plan.get("results", {}).items()
        }
        cache = {"@current": {}}
        for topic in plan["payload"]["topics"]:
            if topic.get("page_id"):
                cache.update(self._notification_cache(c, topic["page_id"]))
        try:
            space = self.store.get_space(plan["space_id"], conn=c)
            for outcome in plan.get("results", {}).values():
                if outcome.get("status") != "completed":
                    continue
                current = c.execute(
                    "SELECT status,version FROM assistant_wiki_pages WHERE workspace_id=%s AND principal_id=%s AND id=%s",
                    (self.workspace_id, self.principal_id, outcome["page_id"]),
                ).fetchone()
                if (
                    not current
                    or current["status"] != "active"
                    or current["version"] != outcome["version"]
                ):
                    return {
                        "confirmable": False,
                        "reason": "已生效对象后来变化，旧审核正文不再展示",
                        "results": safe_results,
                    }
            all_issues = self._plan_block_issues(
                connection=c,
                space=space,
                source_message_id=plan["source_message_id"],
                topics=plan["payload"]["topics"],
                conn=c,
                prepared_sources=cache,
            )
            unsafe = [x for x in all_issues if not x.endswith(":wiki_version_conflict")]
            for topic in plan["payload"]["topics"]:
                for block in topic.get("blocks", []):
                    for ref in block.get("source_refs", []):
                        parts = ref.split(":")
                        if len(parts) != 3:
                            unsafe.append("source_identity_missing")
                            continue
                        current = self.sources.snapshots._build_snapshot(
                            self.sources.snapshots._state(int(parts[1]), conn=c)
                        )
                        if current["revision"] != parts[2]:
                            unsafe.append("source_revision_changed")
            if unsafe:
                return {
                    "confirmable": False,
                    "reason": "来源、记忆或权限已失效，审核正文不可展示",
                    "results": {
                        k: {
                            f: v
                            for f, v in outcome.items()
                            if f in {"status", "page_id", "version"}
                        }
                        for k, outcome in plan.get("results", {}).items()
                    },
                }
            value = self._present_knowledge_plan(
                json.loads(json.dumps(plan)), conn=c, prepared_sources=cache
            )
            if value.get("validation_issues"):
                return {
                    "confirmable": False,
                    "reason": "来源或范围已变化；请从原计划查看当前有效内容",
                    "results": safe_results,
                }
            value["payload"] = {
                k: v
                for k, v in value["payload"].items()
                if k in {"topics", "omitted", "direct_authorized"}
            }
            value["results"] = safe_results
            return value
        except (KeyError, ValueError, AssistantConflict, SourceChangedDuringCapture):
            return {
                "confirmable": False,
                "reason": "无法证明当前来源有效",
                "results": safe_results,
            }

    def notification_proposal(self, c, proposal):
        if proposal["kind"] == "source_patch":
            return self._source_patch_view(c, proposal)
        if not proposal["source_page_id"] or not proposal["source_version"]:
            return {"confirmable": False, "reason": "合并来源页身份不完整"}
        cache = {"@current": {}}
        for pid in (proposal["source_page_id"], proposal["target_page_id"]):
            cache.update(self._notification_cache(c, pid))
        try:
            values = self.list_proposals(
                space_id=proposal["space_id"], conn=c, prepared_sources=cache
            )
        except (AssistantConflict, KeyError, ValueError):
            return {"confirmable": False, "reason": "当前来源证据不可用"}
        return next(
            ({**v, "confirmable": True} for v in values if v["id"] == proposal["id"]),
            {"confirmable": False, "reason": "候选依据已变化或无法证明"},
        )

    def _memories(self):
        """Propagate the verified Wiki principal to every internal Memory edge."""
        return MemoryService(self.db, principal_id=self.principal_id)

    @contextmanager
    def _transaction(self, conn=None, *, operation_key="", page_ids=(), job_claim=None):
        from shiliu.assistant.lease_renewal import check_renewal

        check_renewal()
        with self.db.connect(conn, guard=True) as c:
            self.store.guard_tool_operation(c, operation_key)
            if job_claim is not None:
                guard_job(c, self.db.context, *job_claim)
            if page_ids:
                c.execute(
                    "SELECT id FROM assistant_wiki_pages WHERE workspace_id=%s AND principal_id=%s AND id=ANY(%s) ORDER BY id FOR UPDATE",
                    (self.workspace_id, self.principal_id, list(page_ids)),
                ).fetchall()
            yield c

    def _prepare_sources_for_write(self, space_id=None, page_id=None):
        from shiliu.assistant.wiki_projection import WikiProjection

        if space_id is None:
            with self.db.connect(read_only=True) as c:
                row = c.execute(
                    "SELECT space_id FROM assistant_wiki_pages WHERE workspace_id=%s AND principal_id=%s AND id=%s",
                    (self.workspace_id, self.principal_id, page_id),
                ).fetchone()
            if row is None:
                return {}
            space_id = row["space_id"]
        return WikiProjection(self).prepare_sources(space_id)

    def _require_publish_allowed(
        self, *, connection: Any | None = None, conn=None
    ) -> None:
        if connection is not None and self.publish_transaction_guard is not None:
            self.publish_transaction_guard(connection)
        elif self.publish_allowed is not None and not self.publish_allowed():
            raise MaintenanceYield("maintenance_user_returned")

    def _maintenance_authorized(
        self, payload: dict, *, connection: Any | None = None, conn=None
    ) -> bool:
        """Recheck this Wiki request, or current demand for a shared source job."""
        if connection is None:
            with self.db.connect(conn) as current:
                return self._maintenance_authorized(
                    payload, connection=current, conn=current
                )
        c = connection
        video_id = int(payload["video_id"])
        if payload.get("dirty_generation") is not None:
            dirty = c.execute(
                "SELECT dirty_generation FROM assistant_source_dirty WHERE workspace_id=%s AND video_id=%s",
                (self.workspace_id, video_id),
            ).fetchone()
            if dirty is not None and int(dirty["dirty_generation"]) != int(
                payload["dirty_generation"]
            ):
                return False
        if payload.get("revision"):
            head = c.execute(
                "SELECT current_revision FROM assistant_source_heads WHERE assistant_source_heads.workspace_id=%s AND video_id=%s AND principal_id=%s",
                (
                    self.workspace_id,
                    video_id,
                    self.principal_id,
                ),
            ).fetchone()
            if not head or head["current_revision"] != payload["revision"]:
                return False
        memberships = {
            int(row["source_id"])
            for row in c.execute(
                "SELECT m.source_id FROM video_source_memberships m JOIN favorite_sources s ON s.id=m.source_id JOIN videos v ON v.id=m.video_id WHERE m.workspace_id=%s AND m.video_id=%s AND m.removed_at IS NULL AND s.status='active' AND NOT v.is_ignored AND v.archived_at IS NULL",
                (
                    self.workspace_id,
                    video_id,
                ),
            )
        }
        if not memberships or (
            payload.get("task_subset") and video_id not in payload["task_subset"]
        ):
            return False
        target = payload.get("space_id")
        explicit = False
        basis = payload
        if payload.get("metadata_backfill_intent_id") is not None:
            intent=c.execute("SELECT p.space_id FROM metadata_backfill_wiki_intents i JOIN metadata_backfill_operations o ON (o.workspace_id,o.run_id,o.video_id)=(i.workspace_id,i.run_id,i.video_id) JOIN assistant_wiki_pages p ON (p.workspace_id,p.id)=(i.workspace_id,i.page_id) JOIN assistant_jobs j ON (j.workspace_id,j.id)=(i.workspace_id,i.job_id) WHERE i.workspace_id=%s AND i.id=%s AND i.run_id=%s AND i.video_id=%s AND i.new_revision=%s AND i.state='pending' AND o.state IN ('applied','rollback_pending') AND p.principal_id=%s AND j.principal_id=%s AND j.payload_json=%s",(self.workspace_id,int(payload["metadata_backfill_intent_id"]),str(payload.get("metadata_backfill_run_id") or ""),video_id,str(payload.get("revision") or ""),self.principal_id,self.principal_id,Jsonb(payload))).fetchone()
            if intent is None or target is None or int(target)!=int(intent["space_id"]):
                return False
            explicit=True
        elif payload.get("request_key"):
            root = c.execute(
                "SELECT payload_json FROM assistant_jobs WHERE assistant_jobs.workspace_id=%s AND kind='source_reconcile' AND payload_json->>'request_key'=%s AND (payload_json->>'video_id')::bigint=%s LIMIT 1",
                (
                    self.workspace_id,
                    payload["request_key"],
                    video_id,
                ),
            ).fetchone()
            if not root:
                return False
            basis = root["payload_json"]
            if target is not None and int(target) != int(basis["space_id"]):
                return False
            target, explicit = basis["space_id"], True
        elif payload.get("maintenance_batch_id"):
            batch = c.execute(
                "SELECT space_id FROM assistant_maintenance_batches WHERE assistant_maintenance_batches.workspace_id=%s AND id=%s",
                (
                    self.workspace_id,
                    payload["maintenance_batch_id"],
                ),
            ).fetchone()
            if not batch or (
                target is not None and int(target) != int(batch["space_id"])
            ):
                return False
            target, explicit = batch["space_id"], True
            root = c.execute(
                "SELECT payload_json FROM assistant_jobs WHERE assistant_jobs.workspace_id=%s AND kind='source_reconcile' AND payload_json->>'maintenance_batch_id'=%s AND (payload_json->>'video_id')::bigint=%s LIMIT 1",
                (
                    self.workspace_id,
                    payload["maintenance_batch_id"],
                    video_id,
                ),
            ).fetchone()
            if not root:
                return False
            basis = root["payload_json"]
            if basis.get("scope_version") is None:
                return False
        rows = c.execute(
            "SELECT * FROM assistant_spaces WHERE workspace_id=%s AND principal_id=%s AND enabled=true"
            + (" AND id=%s" if target is not None else ""),
            (self.workspace_id, self.principal_id, target)
            if target is not None
            else (
                self.workspace_id,
                self.principal_id,
            ),
        ).fetchall()
        for row in rows:
            sources, videos = (
                set((row["source_ids_json"])),
                set((row["video_ids_json"])),
            )
            if videos and video_id not in videos:
                continue
            if not (row["all_active"] or memberships.intersection(sources)):
                continue
            if explicit:
                if any(
                    value.get("scope_version") is not None
                    and int(value["scope_version"]) != row["scope_version"]
                    for value in (basis, payload)
                ):
                    return False
                message_id = basis.get("source_message_id")
                if message_id:
                    user = c.execute(
                        "SELECT 1 FROM assistant_messages m JOIN assistant_threads t ON t.id=m.thread_id WHERE m.workspace_id=%s AND m.id=%s AND m.role='user' AND t.space_id=%s AND t.principal_id=%s",
                        (
                            self.workspace_id,
                            message_id,
                            row["id"],
                            self.principal_id,
                        ),
                    ).fetchone()
                    if not user:
                        return False
                    suppressed = c.execute(
                        "SELECT source_message_ids_json FROM assistant_memory_suppressions WHERE assistant_memory_suppressions.workspace_id=%s AND principal_id=%s AND (scope_kind='user' OR (scope_kind='space' AND scope_id=%s))",
                        (
                            self.workspace_id,
                            self.principal_id,
                            str(row["id"]),
                        ),
                    ).fetchall()
                    if any(
                        message_id in (item["source_message_ids_json"])
                        for item in suppressed
                    ):
                        return False
                return True
            if row["maintenance_mode"] == "automatic":
                return True
        if target is None and not explicit:
            # Shared extraction may still be needed by a concurrent explicit request
            # for this generation. No separate consumer registry is necessary.
            roots = c.execute(
                "SELECT payload_json FROM assistant_jobs WHERE assistant_jobs.workspace_id=%s AND kind IN ('source_reconcile','source_extract') AND status IN ('queued','running','retry_wait','budget_wait') AND (payload_json->>'video_id')::bigint=%s AND (payload_json->>'dirty_generation')::bigint=%s AND (payload_json->>'request_key' IS NOT NULL OR payload_json->>'maintenance_batch_id' IS NOT NULL)",
                (
                    self.workspace_id,
                    video_id,
                    payload.get("dirty_generation"),
                ),
            ).fetchall()
            return any(
                self._maintenance_authorized(
                    (row["payload_json"]), connection=c, conn=conn
                )
                for row in roots
            )
        return False

    def _require_maintenance_authorized(
        self, payload: dict, *, connection: Any | None = None, conn=None
    ) -> None:
        if not self._maintenance_authorized(payload, connection=connection, conn=conn):
            raise AssistantConflict("wiki_maintenance_not_authorized")

    def bootstrap_space(
        self,
        space_id: int,
        *,
        limit: int = 5,
        model_budget: int = 30,
        task_subset: list[int] | None = None,
        conn=None,
    ) -> dict[str, Any]:
        if not 1 <= limit <= 10 or not 1 <= model_budget <= 30:
            raise ValueError("invalid_maintenance_budget")
        space = self.store.get_space(space_id, conn=conn)
        video_ids = self.sources.visible_video_ids(
            self._scope({**space, "video_ids": task_subset})
            if task_subset
            else self._scope(space),
            order="collected_desc",
            conn=conn,
        )[: max(1, min(limit, 10))]
        jobs: list[str] = []
        batch_id = f"amb_{uuid.uuid4().hex}"
        with self._transaction(conn) as connection:
            connection.execute(
                "INSERT INTO assistant_maintenance_batches(workspace_id,id,space_id,source_limit,model_limit,calls_used,created_at) VALUES(%s,%s,%s,%s,%s,0,%s)",
                (
                    self.workspace_id,
                    batch_id,
                    space_id,
                    limit,
                    model_budget,
                    utc_now(),
                ),
            )
            for video_id in video_ids:
                generation = self._ensure_dirty(connection, video_id, conn=connection)
                jobs.append(
                    self._enqueue_reconcile(
                        connection,
                        video_id,
                        generation,
                        batch_id=batch_id,
                        task_subset=task_subset,
                        conn=connection,
                    )
                )
        return {
            "space_id": space_id,
            "queued": len(jobs),
            "video_ids": video_ids,
            "job_ids": jobs,
            "batch_id": batch_id,
            "source_limit": limit,
            "model_budget": model_budget,
        }

    def request_topic(
        self,
        *,
        space_id: int,
        topic: str,
        source_refs: list[str],
        request_key: str,
        source_message_id: str | None = None,
        task_subset: list[int] | None = None,
        conn=None,
        review_proposal_id: str | None = None,
    ) -> dict[str, Any]:
        """Queue an explicit, bounded request through the ordinary source pipeline."""
        topic = topic.strip()
        if not topic or len(topic) > 120 or not 1 <= len(source_refs) <= 5:
            raise ValueError("invalid_topic_request")
        space = self.store.get_space(space_id, conn=conn)
        scope = (
            self._scope({**space, "video_ids": task_subset})
            if task_subset
            else self._scope(space)
        )
        if not self.sources.source_refs_visible(
            source_refs, self._scope(space), conn=conn
        ) or not self.sources.source_refs_visible(source_refs, scope, conn=conn):
            raise ValueError("source_out_of_scope")
        video_ids = []
        for ref in source_refs:
            parts = str(ref).split(":", 2)
            if len(parts) < 2 or parts[0] != "video" or not parts[1].isdigit():
                raise ValueError("invalid_source_ref")
            video_ids.append(int(parts[1]))
        if len(set(video_ids)) != len(video_ids):
            raise ValueError("duplicate_source_ref")
        stable_request = (
            f"{space_id}:{hashlib.sha256(request_key.encode('utf-8')).hexdigest()[:24]}"
        )
        jobs = []
        if review_proposal_id:
            stable_request += ":review"
        with self.db.connect(conn) as connection:
            for video_id in video_ids:
                generation = self._ensure_dirty(connection, video_id, conn=connection)
                jobs.append(
                    self.store.enqueue_job(
                        connection,
                        kind="source_reconcile",
                        dedupe_key=f"topic_request:{stable_request}:{video_id}",
                        payload={
                            "video_id": video_id,
                            "dirty_generation": generation,
                            "space_id": space_id,
                            "scope_version": space["scope_version"],
                            "task_topic": topic,
                            "request_key": stable_request,
                            **({"review_proposal_id": review_proposal_id} if review_proposal_id else {}),
                            **({"task_subset": task_subset} if task_subset else {}),
                            **(
                                {"source_message_id": source_message_id}
                                if source_message_id
                                else {}
                            ),
                        },
                    )
                )
            states = [
                str(
                    connection.execute(
                        "SELECT status FROM assistant_jobs WHERE assistant_jobs.workspace_id=%s AND id=%s",
                        (
                            self.workspace_id,
                            job_id,
                        ),
                    ).fetchone()["status"]
                )
                for job_id in jobs
            ]
        status = "accepted"
        if any(value in {"waiting_budget", "blocked"} for value in states):
            status = "waiting_budget"
        elif all(value == "succeeded" for value in states):
            page = self._find_page(space_id, topic, conn=conn)
            linked_ids = (
                {
                    int(ref.split(":", 2)[1])
                    for ref in self.history_source_refs(
                        str(page["id"]), space_id=space_id, conn=conn
                    )
                }
                if page and page.get("blocks")
                else set()
            )
            status = (
                "already_available"
                if set(video_ids).issubset(linked_ids)
                else "no_change"
            )
        return {
            "status": status,
            "topic": topic,
            "queued": sum(
                value in {"queued", "running", "retry_wait"} for value in states
            ),
            "job_ids": jobs,
        }

    def reconcile(self, job: dict[str, Any], *, conn=None) -> dict[str, Any]:
        payload = job["payload"]
        if not self._maintenance_authorized(payload, conn=conn):
            return {"superseded": True, "reason": "wiki_maintenance_not_authorized"}
        video_id = int(payload["video_id"])
        generation = int(payload["dirty_generation"])
        with self.db.connect(conn) as connection:
            current = connection.execute(
                "SELECT dirty_generation FROM assistant_source_dirty WHERE assistant_source_dirty.workspace_id=%s AND video_id=%s",
                (
                    self.workspace_id,
                    video_id,
                ),
            ).fetchone()
        if current is not None and int(current["dirty_generation"]) > generation:
            return {"superseded": True, "reason": "newer_source_generation"}
        task_subset = payload.get("task_subset")
        if not task_subset and payload.get("source_message_id"):
            with self.db.connect(conn) as connection:
                requested = connection.execute(
                    "SELECT r.working_state_json FROM assistant_messages m JOIN assistant_runs r ON r.id=m.run_id WHERE m.workspace_id=%s AND m.id=%s",
                    (
                        self.workspace_id,
                        payload["source_message_id"],
                    ),
                ).fetchone()
            task_subset = (
                ((requested["working_state_json"]).get("task_subset") or {}).get(
                    "video_ids"
                )
                if requested
                else None
            )
        if task_subset and video_id not in task_subset:
            return {"superseded": True, "reason": "task_source_out_of_scope"}
        if payload.get("request_key"):
            space = self.store.get_space(int(payload["space_id"]), conn=conn)
            if int(space["scope_version"]) != int(payload["scope_version"]):
                return {"superseded": True, "reason": "scope_version_changed"}
            if video_id not in self.sources.visible_video_ids(
                self._scope(space), conn=conn
            ):
                return {"superseded": True, "reason": "source_out_of_scope"}
        captured = self.sources.snapshots.capture(
            video_id,
            publish_guard=lambda c: guard_job(
                c, self.db.context, job["id"], job["lease_owner"], job["lease_epoch"]
            ),
        )
        with self._transaction(
            conn, job_claim=(job["id"], job["lease_owner"], job["lease_epoch"])
        ) as connection:
            if not self._maintenance_authorized(
                payload, connection=connection, conn=connection
            ):
                raise AssistantConflict("wiki_maintenance_not_authorized")
            job_id = self.store.enqueue_job(
                connection,
                kind="source_extract",
                dedupe_key=f"source_extract:{captured.revision}:{self.EXTRACTION_VERSION}"
                + (
                    f":batch:{payload['maintenance_batch_id']}"
                    if payload.get("maintenance_batch_id")
                    else ""
                )
                + (
                    f":task:{payload['request_key']}"
                    if payload.get("request_key")
                    else ""
                ),
                payload={
                    "video_id": video_id,
                    "revision": captured.revision,
                    "dirty_generation": generation,
                    "extraction_version": self.EXTRACTION_VERSION,
                    **({"task_subset": task_subset} if task_subset else {}),
                    **(
                        {"maintenance_batch_id": payload["maintenance_batch_id"]}
                        if payload.get("maintenance_batch_id")
                        else {}
                    ),
                    **(
                        {
                            "space_id": payload["space_id"],
                            "scope_version": payload["scope_version"],
                        }
                        if payload.get("space_id") is not None
                        else {}
                    ),
                    **(
                        {
                            "task_topic": payload["task_topic"],
                            "request_key": payload["request_key"],
                            "space_id": payload["space_id"],
                            "scope_version": payload["scope_version"],
                            **(
                                {"source_message_id": payload["source_message_id"]}
                                if payload.get("source_message_id")
                                else {}
                            ),
                        }
                        if payload.get("request_key")
                        else {}
                    ),
                },
            )
            self.store.finish_job(
                job["id"],
                owner=job["lease_owner"],
                lease_epoch=job["lease_epoch"],
                conn=connection,
            )
        # Internal consumer handoff, set only after the business transaction.
        return {
            "revision": captured.revision,
            "source_extract_job_id": job_id,
            "_job_completed": True,
        }

    def extract_source_card(
        self, job: dict[str, Any], *, provider: StructuredProvider, conn=None
    ) -> dict[str, Any]:
        payload = job["payload"]
        if not self._maintenance_authorized(payload, conn=conn):
            return {"superseded": True, "reason": "wiki_maintenance_not_authorized"}
        provider = self._budgeted_provider(payload, provider, job=job, conn=conn)
        staged = job.get("proposal") or {}
        revision = str(payload["revision"])
        video_id = int(payload["video_id"])
        with self.db.connect(conn) as connection:
            card_row = connection.execute(
                "SELECT extraction_version FROM assistant_source_cards WHERE assistant_source_cards.workspace_id=%s AND revision=%s",
                (
                    self.workspace_id,
                    revision,
                ),
            ).fetchone()
        existing = (
            self.get_source_card(revision, conn=conn)
            if card_row and card_row["extraction_version"] == self.EXTRACTION_VERSION
            else None
        )
        if existing is not None:
            self._require_publish_allowed(conn=conn)
            self._enqueue_integrations(
                video_id,
                revision,
                batch_id=payload.get("maintenance_batch_id"),
                task_topic=payload.get("task_topic"),
                request_key=payload.get("request_key"),
                source_message_id=payload.get("source_message_id"),
                task_subset=payload.get("task_subset"),
                expected_scope_version=payload.get("scope_version"),
                conn=conn,
            )
            return {"reused": True, "revision": revision}
        captured = self.sources._capture_or_load(video_id, revision)
        snapshot = captured.snapshot
        input_hash = self._card_input_hash(snapshot)
        with self.db.connect(conn) as connection:
            reusable = connection.execute(
                """
                SELECT card_json FROM assistant_source_cards
                WHERE assistant_source_cards.workspace_id=%s AND video_id=%s AND input_hash=%s AND extraction_version=%s
                ORDER BY updated_at DESC LIMIT 1
                """,
                (
                    self.workspace_id,
                    video_id,
                    input_hash,
                    self.EXTRACTION_VERSION,
                ),
            ).fetchone()
            time_candidates = (
                connection.execute(
                    """SELECT c.revision,c.card_json FROM assistant_source_cards c
                JOIN assistant_source_revisions r ON r.revision=c.revision
                WHERE c.workspace_id=%s AND c.video_id=%s AND r.content_hash=%s AND c.extraction_version=%s
                ORDER BY c.updated_at DESC LIMIT 8""",
                    (
                        self.workspace_id,
                        video_id,
                        snapshot["content_hash"],
                        self.EXTRACTION_VERSION,
                    ),
                ).fetchall()
                if reusable is None
                else []
            )
        if reusable is not None:
            card = reusable["card_json"]
            card["memberships"] = snapshot["memberships"]
            card["metadata_observed_at"] = snapshot["metadata"].get(
                "metadata_observed_at"
            )
        else:
            time_reuse = next(
                (
                    (item["card_json"])
                    for item in time_candidates
                    if self._card_body_equivalent(
                        self.sources._capture_or_load(
                            video_id, str(item["revision"])
                        ).snapshot,
                        snapshot,
                        (item["card_json"]),
                    )
                ),
                None,
            )
            if time_reuse is not None:
                card = dict(time_reuse)
                card["published_at"] = snapshot["metadata"].get("published_at")
                card["memberships"] = snapshot["memberships"]
                card["metadata_observed_at"] = snapshot["metadata"].get(
                    "metadata_observed_at"
                )
                self._require_publish_allowed(conn=conn)
                with self._transaction(
                    conn, job_claim=(job["id"], job["lease_owner"], job["lease_epoch"])
                ) as publish_conn:
                    self._commit_source_card(
                        captured,
                        input_hash=input_hash,
                        card=card,
                        payload=payload,
                        conn=publish_conn,
                    )
                    integration_jobs = self._enqueue_integrations(
                        video_id,
                        revision,
                        batch_id=payload.get("maintenance_batch_id"),
                        task_topic=payload.get("task_topic"),
                        request_key=payload.get("request_key"),
                        source_message_id=payload.get("source_message_id"),
                        task_subset=payload.get("task_subset"),
                        expected_scope_version=payload.get("scope_version"),
                        conn=publish_conn,
                    )
                    self.store.finish_job(
                        job["id"],
                        owner=job["lease_owner"],
                        lease_epoch=job["lease_epoch"],
                        conn=publish_conn,
                    )
                return {
                    "_job_completed": True,
                    "revision": revision,
                    "reused_time_only": True,
                    "integration_job_ids": integration_jobs,
                    "card": card,
                }
            material, material_kind = self._card_material(snapshot)
            if (
                staged.get("kind") == "source_extract"
                and staged.get("input_hash") == input_hash
            ):
                response = staged["response"]
            elif not material.strip():
                response = {
                    "summary": "",
                    "key_points": [],
                    "topics": [],
                    "limitations": ["只有标题或空简介，未生成内容结论"],
                }
            else:
                chunks = [
                    material[index : index + 12000]
                    for index in range(0, len(material), 12000)
                ]
                cursor = max(0, int(payload.get("batch_cursor", 0)))
                stop = min(len(chunks), cursor + 4)
                for batch_index in range(cursor, stop):
                    batch_hash = hashlib.sha256(
                        chunks[batch_index].encode("utf-8")
                    ).hexdigest()
                    with self.db.connect(conn) as connection:
                        saved = connection.execute(
                            "SELECT 1 FROM assistant_source_card_batches WHERE assistant_source_card_batches.workspace_id=%s AND revision=%s AND batch_index=%s AND input_hash=%s",
                            (
                                self.workspace_id,
                                revision,
                                batch_index,
                                batch_hash,
                            ),
                        ).fetchone()
                    if saved:
                        continue
                    self._require_publish_allowed(conn=conn)
                    response = self._extract_batch(
                        provider,
                        snapshot=snapshot,
                        material_kind=material_kind,
                        material=chunks[batch_index],
                        batch_index=batch_index,
                        batch_total=len(chunks),
                        conn=conn,
                    )
                    self._save_card_batch(
                        revision,
                        batch_index=batch_index,
                        input_hash=hashlib.sha256(
                            chunks[batch_index].encode("utf-8")
                        ).hexdigest(),
                        response=response,
                        conn=conn,
                        job=job,
                    )
                if stop < len(chunks):
                    with self.db.connect(conn) as connection:
                        continuation = self.store.enqueue_job(
                            connection,
                            kind="source_extract",
                            dedupe_key=(
                                f"source_extract:{revision}:{self.EXTRACTION_VERSION}:batch:{stop}"
                                + (
                                    f":maintenance:{payload['maintenance_batch_id']}"
                                    if payload.get("maintenance_batch_id")
                                    else ""
                                )
                            ),
                            payload={**payload, "batch_cursor": stop},
                        )
                    return {
                        "partial": True,
                        "revision": revision,
                        "processed_batches": stop,
                        "batch_total": len(chunks),
                        "continuation_job_id": continuation,
                    }
                response = self._merge_card_batches(revision, conn=conn)
            card = self._normalize_card(response, snapshot, material_kind)
        if not (
            staged.get("kind") == "source_extract"
            and staged.get("input_hash") == input_hash
        ) and not self.store.save_job_proposal(
            str(job["id"]),
            {
                "kind": "source_extract",
                "input_hash": input_hash,
                "response": response if reusable is None else card,
            },
            owner=str(job["lease_owner"]),
            lease_epoch=int(job["lease_epoch"]),
            conn=conn,
        ):
            raise MaintenanceYield("maintenance_lease_lost")
        self._require_publish_allowed(conn=conn)
        with self._transaction(
            conn, job_claim=(job["id"], job["lease_owner"], job["lease_epoch"])
        ) as publish_conn:
            self._commit_source_card(
                captured,
                input_hash=input_hash,
                card=card,
                payload=payload,
                conn=publish_conn,
            )
            integration_jobs = self._enqueue_integrations(
                video_id,
                revision,
                batch_id=payload.get("maintenance_batch_id"),
                task_topic=payload.get("task_topic"),
                request_key=payload.get("request_key"),
                source_message_id=payload.get("source_message_id"),
                task_subset=payload.get("task_subset"),
                expected_scope_version=payload.get("scope_version"),
                conn=publish_conn,
            )
            self.store.finish_job(
                job["id"],
                owner=job["lease_owner"],
                lease_epoch=job["lease_epoch"],
                conn=publish_conn,
            )
        return {
            "_job_completed": True,
            "revision": revision,
            "integration_job_ids": integration_jobs,
            "card": card,
        }

    def integrate_source_card(
        self, job: dict[str, Any], *, provider: StructuredProvider, conn=None
    ) -> dict[str, Any]:
        payload = job["payload"]
        if not self._maintenance_authorized(payload, conn=conn):
            return {"superseded": True, "reason": "wiki_maintenance_not_authorized"}
        provider = self._budgeted_provider(payload, provider, job=job, conn=conn)
        staged = job.get("proposal") or {}
        space = self.store.get_space(int(payload["space_id"]), conn=conn)
        if int(space["scope_version"]) != int(payload["scope_version"]):
            return {"superseded": True, "reason": "scope_version_changed"}
        video_id = int(payload["video_id"])
        if video_id not in self.sources.visible_video_ids(
            self._scope(space), conn=conn
        ):
            return {"superseded": True, "reason": "source_out_of_scope"}
        task_scope = None
        if payload.get("task_subset"):
            allowed = set(self.sources.visible_video_ids(self._scope(space), conn=conn))
            selected = sorted(
                allowed.intersection(int(v) for v in payload["task_subset"])
            )
            if video_id not in selected:
                return {"superseded": True, "reason": "task_source_out_of_scope"}
            space = {**space, "video_ids": selected}
            task_scope = self._scope(space)
        revision = str(payload["revision"])
        with self.db.connect(conn) as connection:
            head = connection.execute(
                """SELECT current_revision FROM assistant_source_heads
                WHERE assistant_source_heads.workspace_id=%s AND principal_id=%s AND video_id=%s""",
                (
                    self.workspace_id,
                    self.principal_id,
                    video_id,
                ),
            ).fetchone()
        if head is None or str(head["current_revision"] or "") != revision:
            return {"superseded": True, "reason": "source_revision_changed"}
        card = self.get_source_card(revision, conn=conn)
        if card is None:
            raise RuntimeError("source_card_missing")
        if not card.get("summary") and not card.get("key_points"):
            return {
                "no_change": True,
                "reason": "insufficient_material",
                "revision": revision,
            }
        topic = (
            str(
                payload.get("task_topic")
                or payload.get("topic")
                or (card.get("topics") or [card["title"]])[0]
            ).strip()
            or card["title"]
        )
        existing = self._find_page(int(space["id"]), topic, conn=conn)
        if existing is not None and existing["status"] != "active":
            return {
                "no_change": True,
                "reason": "wiki_page_inactive",
                "page_id": existing["id"],
            }
        if payload.get("repair_page_id") and (
            existing is None or str(existing["id"]) != str(payload["repair_page_id"])
        ):
            return {"superseded": True, "reason": "repair_page_changed"}
        fuzzy_candidate = existing is None
        if existing is None and not payload.get("task_topic"):
            existing = self._find_related_page(
                int(space["id"]), {**card, "topics": [topic]}, conn=conn
            )
        current_existing = (
            self._task_projection(
                self._visible_page(existing, conn=conn), task_scope, conn=conn
            )
            if existing is not None
            else None
        )
        if task_scope is not None and current_existing is not None:
            current_existing["blocks"] = [
                {
                    **block,
                    "source_refs": [
                        ref.split(":", 2)[2]
                        if ref.startswith("video:") and len(ref.split(":", 2)) == 3
                        else ref
                        for ref in block.get("source_refs", [])
                    ],
                }
                for block in current_existing["blocks"]
            ]
        visible_block_ids = {
            str(block["stable_id"])
            for block in (current_existing or {}).get("blocks", [])
        }
        if existing is not None:
            with self.db.connect(conn) as connection:
                material_link = connection.execute(
                    """SELECT source_revision,relation FROM assistant_wiki_materials
                    WHERE assistant_wiki_materials.workspace_id=%s AND page_id=%s AND video_id=%s""",
                    (
                        self.workspace_id,
                        existing["id"],
                        video_id,
                    ),
                ).fetchone()
                duplicate_content = connection.execute(
                    """
                    SELECT 1 FROM assistant_wiki_dependencies d
                    JOIN assistant_source_cards old_card ON old_card.revision=d.source_revision
                    JOIN assistant_source_cards new_card ON new_card.revision=%s
                    WHERE d.workspace_id=%s AND d.page_id=%s AND d.video_id=%s
                      AND old_card.input_hash=new_card.input_hash
                      AND d.source_revision<>%s LIMIT 1
                    """,
                    (
                        revision,
                        self.workspace_id,
                        existing["id"],
                        video_id,
                        revision,
                    ),
                ).fetchone()
                old_revisions = [
                    str(item["source_revision"])
                    for item in connection.execute(
                        """SELECT DISTINCT source_revision FROM assistant_wiki_dependencies
                    WHERE assistant_wiki_dependencies.workspace_id=%s AND page_id=%s AND video_id=%s AND source_revision<>%s""",
                        (
                            self.workspace_id,
                            existing["id"],
                            video_id,
                            revision,
                        ),
                    ).fetchall()
                ]
            if duplicate_content is None and old_revisions:
                new_snapshot = self.sources._capture_or_load(
                    video_id, revision
                ).snapshot
                duplicate_content = next(
                    (
                        old_revision
                        for old_revision in old_revisions
                        if self._card_body_equivalent(
                            self.sources._capture_or_load(
                                video_id, old_revision
                            ).snapshot,
                            new_snapshot,
                            self.get_source_card(old_revision, conn=conn) or {},
                        )
                    ),
                    None,
                )
            if (
                material_link is not None
                and str(material_link["source_revision"]) == revision
                and (
                    str(material_link["relation"]) == "associated"
                    or (
                        current_existing
                        and current_existing["availability"] == "full"
                        and any(
                            revision in block.get("source_refs", [])
                            and block.get("compiler_version") == self.COMPILER_VERSION
                            for block in current_existing["blocks"]
                        )
                    )
                )
            ):
                return {
                    "no_change": True,
                    "reason": "material_already_processed",
                    "page_id": existing["id"],
                    "version": existing["version"],
                }
            if duplicate_content is not None:
                self._require_publish_allowed(conn=conn)
                return self._rebind_equivalent_source(
                    existing,
                    space=space,
                    video_id=video_id,
                    revision=revision,
                    job=job,
                    conn=conn,
                )
        if (
            existing
            and current_existing
            and current_existing["availability"] == "full"
            and any(
                revision in block.get("source_refs", [])
                and block.get("compiler_version") == self.COMPILER_VERSION
                for block in current_existing["blocks"]
            )
        ):
            return {
                "no_change": True,
                "page_id": existing["id"],
                "version": existing["version"],
            }
        catalog_revisions = [revision]
        if existing is not None:
            catalog_revisions.extend(
                self._current_page_source_revisions(
                    str(existing["id"]), space=space, conn=conn
                )
            )
        catalog_revisions = list(dict.fromkeys(catalog_revisions))[:6]
        source_key_map = {
            f"s{index + 1}": value for index, value in enumerate(catalog_revisions)
        }
        invalid_block_directory = [
            {
                "id": block["stable_id"],
                "heading": str(block["heading"])[:120],
                "current_source_keys": [
                    key
                    for key, value in source_key_map.items()
                    if value in block.get("source_refs", [])
                ],
            }
            for block in (existing or {}).get("blocks", [])
            if block["stable_id"] not in visible_block_ids
            and block.get("source_refs")
            and task_scope is None
        ]
        source_catalog = [
            {
                "key": key,
                "card": {
                    field: value
                    for field, value in (
                        self.get_source_card(source_revision) or {}
                    ).items()
                    if field
                    in {
                        "title",
                        "uploader",
                        "published_at",
                        "coverage",
                        "material_kind",
                        "summary",
                        "key_points",
                        "limitations",
                    }
                },
            }
            for key, source_revision in source_key_map.items()
        ]
        basis = {
            "revision": revision,
            "scope_version": int(space["scope_version"]),
            "page_id": (existing or {}).get("id"),
            "page_version": (existing or {}).get("version"),
            "source_keys": source_key_map,
            "task_subset": payload.get("task_subset"),
            "topic": topic,
            "compiler": self.COMPILER_VERSION,
        }
        basis_hash = hashlib.sha256(
            json.dumps(basis, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        reuse_staged = (
            staged.get("kind") == "wiki_integrate"
            and staged.get("basis_hash") == basis_hash
        )
        if reuse_staged:
            provider = _StoredResponseProvider(staged["response"])
        response = provider.generate_json(
            system=(
                "你是拾流 Wiki 局部编译器。按问题组织已有主题页与本次 SourceCard。"
                "已有页面优先只增补或修订受影响的说法，不重写整页；每次只读有限材料。"
                "每个新块须说明它帮助回答主题中的哪个实际问题；仅与来源卡有关而对用途无帮助的信息不要入页。"
                "比较时逐方保留主体、条件与明确动作。某材料未说默认开关或频率，不能推成默认开启或直接矛盾。"
                "保留上传者、发言者、被引出处与注释的角色差异；未知归属留未知。"
                "转载不算独立核实，引用官方不等于已读官方原文；有不同条件时不要制造共识。返回 JSON。"
            ),
            prompt=(
                "返回 {same_topic,title,page_type,summary,operation,target_block_id,blocks:[{heading,markdown,applicability,assessment,relation,source_keys,speaker,cited_source,evidence_quote}]}。"
                "已有页 operation 只能为 add_block/revise_block/associate/no_change；新增页可省略 operation。"
                "add_block 只写有新价值的一块，source_keys 必须包括新材料 s1；revise_block 指定目录中的非人工块，"
                "保留该块仍需要的有效来源；associate 表示材料相关但不支持现有说法，不能伪造支持。"
                "失效块目录只给位置、不含旧正文。需要修复时仅据当前材料写更窄的新说法，不能恢复旧正文。"
                "若给了候选旧页，same_topic 只有问题边界确实一致才为 true；同词或相似领域不足以合并。"
                "若边界不同，same_topic=false，summary/blocks 只能用新材料 key=s1。"
                "page_type 只能是 concept/method/comparison/topic；summary 是围绕 topic 的短导读，"
                "blocks 是重组后的完整来源型主题块，最多 5 块；每块 source_keys 仅列真正支持该说法的材料 key，"
                "只有旧式完整重组才须保留 source_catalog 中每份仍有效材料的有据块。"
                "不同条件不能混成共识。同源转述不能算独立核实。个人手写块由程序保护，不需返回。"
                "没有新增价值可返回空 blocks。不要引用未在输入中定位的原文。"
                "歌词准确性只在引用歌词的主题中相关；一般器材供应、通用免责声明不能挤占运镜方法或作品参考。\n"
                + json.dumps(
                    {
                        "topic": topic,
                        "existing_page": self._page_for_prompt(
                            current_existing, source_key_map=source_key_map
                        ),
                        "page_directory": [
                            {
                                "id": block["stable_id"],
                                "heading": block["heading"][:100],
                                "applicability": str(block.get("applicability") or "")[
                                    :160
                                ],
                                "manual": bool(block.get("manual_lock")),
                                "source_count": len(block.get("source_refs", [])),
                            }
                            for block in (current_existing or {}).get("blocks", [])[:80]
                        ],
                        "invalid_block_directory": invalid_block_directory[:20],
                        "repair_requested": bool(payload.get("repair_page_id")),
                        "source_card": card,
                        "source_catalog": source_catalog,
                    },
                    ensure_ascii=False,
                )
            ),
            max_tokens=2600,
        )
        if not reuse_staged and not self.store.save_job_proposal(
            str(job["id"]),
            {"kind": "wiki_integrate", "response": response, "basis_hash": basis_hash},
            owner=str(job["lease_owner"]),
            lease_epoch=int(job["lease_epoch"]),
            conn=conn,
        ):
            return {"superseded": True, "reason": "wiki_job_lease_lost"}
        self._require_publish_allowed(conn=conn)
        if (
            fuzzy_candidate
            and existing is not None
            and response.get("same_topic") is not True
        ):
            existing = None
            source_key_map = {"s1": revision}
            if not payload.get("task_topic") and not payload.get(
                "maintenance_batch_id"
            ):
                return {
                    "no_change": True,
                    "reason": "no_existing_topic_match",
                    "revision": revision,
                }
        patch = self._normalize_wiki_patch(
            response,
            topic=topic,
            card=card,
            revision=revision,
            source_key_map=source_key_map,
            source_titles={
                item["key"]: str(item["card"].get("title") or "材料")
                for item in source_catalog
            },
        )
        local_operation = (
            str(response.get("operation") or "") if existing is not None else ""
        )
        if local_operation not in {
            "add_block",
            "revise_block",
            "associate",
            "no_change",
        }:
            local_operation = ""
        if task_scope is not None and existing is not None:
            # A subset may only patch a visible non-manual block or append one.
            # Legacy whole-page regeneration would erase excluded history.
            if local_operation not in {
                "add_block",
                "revise_block",
                "associate",
                "no_change",
            }:
                raise ValueError("task_subset_requires_local_patch")
            if (
                local_operation == "revise_block"
                and str(response.get("target_block_id") or "") not in visible_block_ids
            ):
                raise ValueError("task_subset_target_out_of_scope")
        if (
            payload.get("repair_page_id")
            and not payload.get("review_proposal_id")
            and invalid_block_directory
            and (
                local_operation != "revise_block"
                or str(response.get("target_block_id") or "")
                not in {str(item["id"]) for item in invalid_block_directory}
            )
        ):
            return {
                "no_change": True,
                "reason": "repair_requires_current_supported_revision",
                "page_id": existing["id"],
                "version": existing["version"],
            }
        if local_operation == "no_change":
            return {
                "no_change": True,
                "reason": "no_new_topic_value",
                "revision": revision,
                "page_id": existing["id"],
                "version": existing["version"],
            }
        if local_operation in {"add_block", "revise_block"}:
            patch["blocks"] = patch["blocks"][:1]
            if not patch["blocks"] or revision not in patch["blocks"][0].get(
                "source_refs", []
            ):
                return {
                    "no_change": True,
                    "reason": "proposal_missing_new_source_support",
                    "revision": revision,
                }
            patch["replace_derived"] = False
            patch["local_operation"] = local_operation
            patch["target_block_id"] = str(response.get("target_block_id") or "") if local_operation == "revise_block" else ""
            # Preserve a currently valid guide; a partial page must not reuse
            # prose that may summarize a withdrawn source.
            if local_operation == "revise_block":
                patch["summary"] = self._pending_guide()
            elif current_existing and current_existing["availability"] == "full":
                prior_guide = str(current_existing.get("summary") or "")[:1800]
                patch["summary"] = (
                    prior_guide
                    + f" 新增对照：{patch['blocks'][0]['heading']}；具体条件与出处见对应内容。"
                )[:2200]
            else:
                patch["summary"] = (
                    f"本主题已按当前材料更新「{patch['blocks'][0]['heading']}」；"
                    "其他失效内容仍待核对，请逐条查看来源。"
                )
        elif local_operation == "associate":
            patch["blocks"] = []
            patch["replace_derived"] = False
            patch["local_operation"] = "associate"
            patch["summary"] = str((current_existing or {}).get("summary") or "")
        if not patch["blocks"] and local_operation != "associate":
            return {
                "no_change": True,
                "reason": "no_new_topic_value",
                "revision": revision,
                **(
                    {"page_id": existing["id"], "version": existing["version"]}
                    if existing
                    else {}
                ),
            }
        if patch.get("replace_derived") and not local_operation:
            covered = {
                ref for block in patch["blocks"] for ref in block.get("source_refs", [])
            }
            if not set(catalog_revisions).issubset(covered):
                return {
                    "no_change": True,
                    "reason": "proposal_missing_source_coverage",
                    "revision": revision,
                    **(
                        {"page_id": existing["id"], "version": existing["version"]}
                        if existing
                        else {}
                    ),
                }
        patch["aliases"] = [topic]
        if existing is not None:
            # The candidate was selected from local lexical evidence. Keeping its
            # canonical title prevents a model paraphrase from creating a near-duplicate page.
            patch["title"] = existing["title"]
        expected_version = int(existing["version"]) if existing else 0
        try:
            page = self.apply_patch(
                space_id=int(space["id"]),
                video_id=video_id,
                revision=revision,
                expected_version=expected_version,
                patch=patch,
                scope_version=int(space["scope_version"]),
                job_id=str(job["id"]),
                lease_owner=str(job["lease_owner"]),
                lease_epoch=int(job["lease_epoch"]),
                conn=conn,
            )
        except AssistantConflict as exc:
            if str(exc) == "proposal_missing_source_coverage":
                return {"no_change": True, "reason": str(exc), "revision": revision}
            if str(exc) in {
                "wiki_job_lease_lost",
                "wiki_job_payload_changed",
                "wiki_scope_changed",
                "wiki_source_out_of_scope",
                "source_revision_changed",
                "wiki_task_input_stale",
            }:
                return {"superseded": True, "reason": str(exc)}
            raise
        if page.get("proposal_id"):
            return {"_job_completed": True, **page}
        return {
            "_job_completed": True,
            "page_id": page["id"],
            "version": page["version"],
            "title": page["title"],
        }

    def _rebind_equivalent_source(
        self,
        page: dict[str, Any],
        *,
        space: dict[str, Any],
        video_id: int,
        revision: str,
        job: dict[str, Any],
        conn=None,
        prepared_sources=None,
    ) -> dict[str, Any]:
        """Advance an equivalent card's provenance without another model call."""
        prepared = prepared_sources if prepared_sources is not None else self._prepare_sources_for_write(space_id=int(space["id"]))
        if revision not in prepared:
            prepared[revision] = self.sources._capture_or_load(
                video_id, revision
            ).snapshot
        now = utc_now()
        with self._transaction(
            conn,
            job_claim=(job["id"], job["lease_owner"], job["lease_epoch"]),
            page_ids=[page["id"]],
        ) as connection:
            self._require_publish_allowed(connection=connection, conn=connection)
            self._validate_wiki_commit_fence(
                connection,
                space_id=int(space["id"]),
                video_id=video_id,
                revision=revision,
                scope_version=int(space["scope_version"]),
                job_id=str(job["id"]),
                lease_owner=str(job["lease_owner"]),
                lease_epoch=int(job["lease_epoch"]),
                now=now,
                conn=connection,
            )
            row = connection.execute(
                "SELECT * FROM assistant_wiki_pages WHERE assistant_wiki_pages.workspace_id=%s AND id=%s AND status='active'",
                (
                    self.workspace_id,
                    page["id"],
                ),
            ).fetchone()
            if row is None or int(row["version"]) != int(page["version"]):
                raise AssistantConflict("wiki_version_conflict")
            before = self._decode_page(dict(row))
            before_state = self._operation_state(
                connection, str(page["id"]), conn=connection
            )
            old_rows = connection.execute(
                """SELECT DISTINCT d.source_revision,old_card.input_hash AS old_hash,
                       new_card.input_hash AS new_hash
                FROM assistant_wiki_dependencies d
                JOIN assistant_source_cards old_card ON old_card.revision=d.source_revision
                JOIN assistant_source_cards new_card ON new_card.revision=%s
                WHERE d.workspace_id=%s AND d.page_id=%s AND d.video_id=%s AND d.source_revision<>%s
                  AND d.block_id NOT IN (SELECT value->>'stable_id' FROM assistant_wiki_pages p,jsonb_array_elements(p.blocks_json) AS b(value) WHERE p.id=d.page_id AND coalesce((value->>'deleted')::boolean,false))""",
                (
                    revision,
                    self.workspace_id,
                    page["id"],
                    video_id,
                    revision,
                ),
            ).fetchall()
            new_snapshot = prepared[revision]
            old_revisions = {
                str(item["source_revision"])
                for item in old_rows
                if item["old_hash"] == item["new_hash"]
                or self._card_body_equivalent(
                    prepared[str(item["source_revision"])],
                    new_snapshot,
                    self.get_source_card(str(item["source_revision"]), conn=connection)
                    or {},
                )
            }
            if not old_revisions:
                self.store.finish_job(
                    job["id"],
                    owner=job["lease_owner"],
                    lease_epoch=job["lease_epoch"],
                    conn=connection,
                )
                return {
                    "_job_completed": True,
                    "no_change": True,
                    "reason": "equivalent_source_already_current",
                    "page_id": page["id"],
                    "version": page["version"],
                }
            blocks = []
            for block in before["blocks"]:
                item = dict(block)
                if item.get("deleted"):
                    blocks.append(item)
                    continue
                item["source_refs"] = list(
                    dict.fromkeys(
                        revision if ref in old_revisions else ref
                        for ref in item.get("source_refs", [])
                    )
                )
                blocks.append(item)
            for old_revision in old_revisions:
                connection.execute(
                    """INSERT INTO assistant_wiki_dependencies(workspace_id,
                        page_id,block_id,source_revision,video_id,dependency_kind,created_at
                    ) SELECT %s, page_id,block_id,%s,video_id,dependency_kind,%s
                      FROM assistant_wiki_dependencies
                      WHERE page_id=%s AND video_id=%s AND source_revision=%s
                      AND block_id NOT IN (SELECT value->>'stable_id' FROM assistant_wiki_pages p,jsonb_array_elements(p.blocks_json) AS b(value) WHERE p.id=%s AND coalesce((value->>'deleted')::boolean,false)) ON CONFLICT DO NOTHING""",
                    (
                        self.workspace_id,
                        revision,
                        now,
                        page["id"],
                        video_id,
                        old_revision,
                        page["id"],
                    ),
                )
                connection.execute(
                    """DELETE FROM assistant_wiki_dependencies WHERE assistant_wiki_dependencies.workspace_id=%s AND page_id=%s AND video_id=%s AND source_revision=%s
                    AND block_id NOT IN (SELECT value->>'stable_id' FROM assistant_wiki_pages p,jsonb_array_elements(p.blocks_json) AS b(value) WHERE p.id=%s AND coalesce((value->>'deleted')::boolean,false))""",
                    (
                        self.workspace_id,
                        page["id"],
                        video_id,
                        old_revision,
                        page["id"],
                    ),
                )
            version = int(before["version"]) + 1
            connection.execute(
                "UPDATE assistant_wiki_pages SET blocks_json=%s, version=%s, scope_version=%s, updated_at=%s WHERE assistant_wiki_pages.workspace_id=%s AND id=%s",
                (
                    Jsonb(blocks),
                    version,
                    int(space["scope_version"]),
                    now,
                    self.workspace_id,
                    page["id"],
                ),
            )
            connection.execute(
                """UPDATE assistant_wiki_materials SET source_revision=%s, updated_at=%s
                WHERE assistant_wiki_materials.workspace_id=%s AND page_id=%s AND video_id=%s""",
                (
                    revision,
                    now,
                    self.workspace_id,
                    page["id"],
                    video_id,
                ),
            )
            after = self._decode_page(
                dict(
                    connection.execute(
                        "SELECT * FROM assistant_wiki_pages WHERE assistant_wiki_pages.workspace_id=%s AND id=%s",
                        (
                            self.workspace_id,
                            page["id"],
                        ),
                    ).fetchone()
                )
            )
            self._record_notification_change(
                connection,
                """INSERT INTO assistant_wiki_changes(workspace_id,
                    page_id,version,operation,before_json,after_json,summary,actor,created_at
                ) VALUES(%s,%s,%s,'source_rebound',%s,%s,%s,'assistant',%s)""",
                (
                    self.workspace_id,
                    page["id"],
                    version,
                    Jsonb(before),
                    Jsonb(after),
                    "等价材料的来源版本已更新",
                    now,
                ),
                cause={"job_id": job["id"], "video_id": video_id},
            )
            self._save_operation_state(
                connection, str(page["id"]), version, before_state, conn=connection
            )
            self.store.finish_job(
                job["id"],
                owner=job["lease_owner"],
                lease_epoch=job["lease_epoch"],
                conn=connection,
            )
        return {
            "_job_completed": True,
            "page_id": page["id"],
            "version": version,
            "no_model_call": True,
            "reason": "equivalent_source_rebound",
        }

    def _source_direct_authorized(self, c, payload):
        """Maintenance eligibility alone never grants unattended body publication."""
        if not self._maintenance_authorized(payload, connection=c, conn=c):
            raise AssistantConflict("wiki_maintenance_not_authorized")
        key, batch = payload.get("request_key"), payload.get("maintenance_batch_id")
        if not key and not batch:
            return False  # Internal backfill/repair intents also require review.
        roots = c.execute(
            "SELECT payload_json,dedupe_key FROM assistant_jobs WHERE workspace_id=%s AND principal_id=%s AND kind='source_reconcile' AND (payload_json->>'video_id')::bigint=%s",
            (self.workspace_id, self.principal_id, int(payload["video_id"])),
        ).fetchall()
        for root in roots:
            basis = root["payload_json"]
            if key:
                if (
                    basis.get("request_key") != key
                    or root["dedupe_key"]
                    != f"topic_request:{key}:{payload['video_id']}"
                ):
                    continue
                fields = (
                    "space_id",
                    "scope_version",
                    "task_topic",
                    "task_subset",
                    "source_message_id",
                )
            else:
                if basis.get("maintenance_batch_id") != batch:
                    continue
                fields = ("space_id", "scope_version", "task_subset")
            if any(basis.get(f) != payload.get(f) for f in fields):
                continue
            # Refresh requests authorize recomputation only, never publication.
            return not str(key or "").endswith(":review") and not basis.get(
                "review_proposal_id"
            )
        raise AssistantConflict("wiki_direct_request_basis_mismatch")

    def _source_proposal(self, c, identity, *, space_id=None):
        row = c.execute(
            "SELECT * FROM assistant_wiki_proposals WHERE workspace_id=%s AND principal_id=%s AND id=%s",
            (self.workspace_id, self.principal_id, identity),
        ).fetchone()
        if not row or (space_id is not None and row["space_id"] != space_id):
            raise KeyError(identity)
        return dict(row)

    def _expire_source_patches(self, c, page_id, *, exclude=None):
        c.execute(
            "UPDATE assistant_wiki_proposals SET status='stale',decided_at=clock_timestamp(),updated_at=clock_timestamp(),payload_json=jsonb_set(payload_json,'{decision_reason}','\"target_page_changed_or_superseded\"') WHERE workspace_id=%s AND principal_id=%s AND kind='source_patch' AND status='pending' AND target_page_id=%s AND (%s::text IS NULL OR id<>%s)",
            (self.workspace_id, self.principal_id, page_id, exclude, exclude),
        )

    def _source_patch_evidence(self, proposal):
        """Prepare immutable material outside the protected decision transaction."""
        from shiliu.assistant.wiki_projection import WikiProjection

        data = proposal["payload_json"]
        revisions = {data["revision"], *data["source_revisions"]}
        revisions.update(
            ref for b in data["patch"]["blocks"] for ref in b.get("source_refs", [])
        )
        cache = {"@current": {}}
        with self.db.connect(read_only=True) as c:
            for revision in revisions:
                row = c.execute(
                    "SELECT video_id FROM assistant_source_heads WHERE workspace_id=%s AND principal_id=%s AND current_revision=%s",
                    (self.workspace_id, self.principal_id, revision),
                ).fetchone()
                if not row:
                    raise AssistantConflict("source_revision_changed")
                vid = row["video_id"]
                state = self.sources.snapshots._state(vid, conn=c)
                actual = self.sources.snapshots._build_snapshot(state)
                saved = self.sources.snapshots.load(vid, revision)
                if actual["revision"] != revision or saved.snapshot != actual:
                    raise AssistantConflict("source_revision_changed")
                cache[revision] = actual
                cache["@current"][vid] = {
                    "revision": revision,
                    "token": WikiProjection._state_token(state),
                }
        return cache

    def _validate_source_patch(self, c, proposal, *, lock=False, prepared=None):
        data = proposal["payload_json"]
        request = data["request"]
        space = self.store.get_space(proposal["space_id"], conn=c)
        self._validate_source_scope(
            c,
            space_id=space["id"],
            video_id=data["video_id"],
            revision=data["revision"],
            scope_version=data["scope_version"],
        )
        origin = c.execute(
            "SELECT payload_json FROM assistant_jobs WHERE workspace_id=%s AND principal_id=%s AND id=%s AND kind='wiki_integrate'",
            (self.workspace_id, self.principal_id, data["origin_job_id"]),
        ).fetchone()
        if not origin or origin["payload_json"] != request:
            raise AssistantConflict("wiki_proposal_origin_changed")
        row = c.execute(
            "SELECT * FROM assistant_wiki_pages WHERE workspace_id=%s AND principal_id=%s AND space_id=%s AND id=%s"
            + (" FOR UPDATE" if lock else ""),
            (
                self.workspace_id,
                self.principal_id,
                space["id"],
                proposal["target_page_id"],
            ),
        ).fetchone()
        if not row:
            raise AssistantConflict("wiki_page_missing")
        page = self._decode_page(dict(row))
        if page["version"] != proposal["target_version"]:
            raise AssistantConflict("wiki_version_conflict")
        patch = data["patch"]
        if patch.get("local_operation") not in {
            "add_block",
            "revise_block",
        } or patch.get("replace_derived"):
            raise AssistantConflict("wiki_proposal_operation_invalid")
        self._assert_lifecycle(
            page, patch["blocks"], target_id=patch.get("target_block_id", "")
        )
        space_allowed = set(self.sources.visible_video_ids(self._scope(space), conn=c))
        allowed = (
            space_allowed.intersection(request["task_subset"])
            if request.get("task_subset")
            else space_allowed
        )
        # Freeze the reviewed, current source basis plus incoming evidence.
        # Legacy proposals retain their saved (stricter) source_revisions list.
        # A stale SQL head is insufficient: verify actual Snapshot identity.
        revisions = {data["revision"], *data["source_revisions"]}
        revisions.update(
            ref for b in patch["blocks"] for ref in b.get("source_refs", [])
        )
        for revision in revisions:
            head = c.execute(
                "SELECT video_id FROM assistant_source_heads WHERE workspace_id=%s AND principal_id=%s AND current_revision=%s",
                (self.workspace_id, self.principal_id, revision),
            ).fetchone()
            incoming = revision in {
                data["revision"],
                *(ref for b in patch["blocks"] for ref in b.get("source_refs", [])),
            }
            if not head or head["video_id"] not in (
                allowed if incoming else space_allowed
            ):
                raise AssistantConflict("wiki_source_out_of_scope")
            vid = head["video_id"]
            state = self.sources.snapshots._state(vid, conn=c)
            if prepared is not None:
                from shiliu.assistant.wiki_projection import WikiProjection

                expected = prepared["@current"].get(vid)
                if (
                    not expected
                    or expected["revision"] != revision
                    or expected["token"] != WikiProjection._state_token(state)
                ):
                    raise AssistantConflict("source_revision_changed")
            else:
                actual = self.sources.snapshots._build_snapshot(state)
                saved = self.sources.snapshots.load(vid, revision)
                if actual["revision"] != revision or saved.snapshot != actual:
                    raise AssistantConflict("source_revision_changed")
        cache = (
            prepared
            if prepared is not None
            else self._notification_cache(c, page["id"])
        )
        visible = self._visible_page(page, conn=c, snapshot_cache=cache)
        if request.get("task_subset"):
            visible = self._task_projection(
                visible, self._scope({**space, "video_ids": sorted(allowed)}), conn=c
            )
        if patch["local_operation"] == "revise_block":
            target = next(
                (
                    b
                    for b in visible["blocks"]
                    if b["stable_id"] == patch["target_block_id"]
                ),
                None,
            )
            if not target or target.get("manual_lock"):
                raise AssistantConflict("wiki_manual_conflict")
        current_refs = set(
            self._current_page_source_revisions(page["id"], space=space, conn=c)
        )
        incoming_refs = {
            ref for b in patch["blocks"] for ref in b.get("source_refs", [])
        }
        if patch["local_operation"] == "revise_block" and not (
            set(target.get("source_refs", [])) & current_refs
        ).issubset(incoming_refs):
            raise AssistantConflict("proposal_missing_source_coverage")
        retained = incoming_refs | {
            ref
            for b in page["blocks"]
            if patch["local_operation"] != "revise_block"
            or b["stable_id"] != patch["target_block_id"]
            for ref in b.get("source_refs", [])
        }
        if not current_refs.issubset(retained) or data["revision"] not in retained:
            raise AssistantConflict("proposal_missing_source_coverage")
        for dep in c.execute(
            "SELECT * FROM assistant_wiki_personal_dependencies WHERE workspace_id=%s AND page_id=%s",
            (self.workspace_id, page["id"]),
        ).fetchall():
            if not self._personal_dependency_current(
                c,
                memory_id=dep["memory_id"],
                memory_version=dep["memory_version"],
                source_message_id=dep["source_message_id"],
                space_id=space["id"],
                conn=c,
            ):
                raise AssistantConflict("wiki_personal_dependency_changed")
        # Original request message suppression must still hold for review commands.
        if request.get("source_message_id"):
            suppressed = self._memories().suppressed_source_message_ids(
                space_id=space["id"], conn=c
            )
            if request["source_message_id"] in suppressed:
                raise AssistantConflict("wiki_task_input_stale")
        return page

    def _create_source_patch(self, c, request, patch, target_version, job_id):
        page = self._find_page(request["space_id"], patch["title"], conn=c)
        if not page:
            raise AssistantConflict("wiki_page_missing")
        data = {
            "patch": patch,
            "before": page,
            "scope_version": request["scope_version"],
            "video_id": request["video_id"],
            "revision": request["revision"],
            # Untouched stale history is not evidence for this local patch.
            # Keep it in before/page history and retain its existing hidden
            # state. Valid original evidence is frozen for approval rechecks.
            "source_revisions": self._current_page_source_revisions(
                page["id"], space=self.store.get_space(request["space_id"], conn=c), conn=c
            ),
            "compiler": self.COMPILER_VERSION,
            "request": request,
            "origin_job_id": job_id,
        }
        content = {
            k: v for k, v in data.items() if k not in {"origin_job_id", "request"}
        }
        content["before"] = {
            k: page[k] for k in ("id", "version", "title", "summary", "blocks")
        }
        content["task_subset"] = request.get("task_subset")
        fingerprint = hashlib.sha256(
            json.dumps(
                content, sort_keys=True, ensure_ascii=False, default=str
            ).encode()
        ).hexdigest()
        previous = c.execute(
            "SELECT * FROM assistant_wiki_proposals WHERE workspace_id=%s AND principal_id=%s AND space_id=%s AND kind='source_patch' AND target_page_id=%s ORDER BY content_version DESC,created_at DESC LIMIT 1",
            (self.workspace_id, self.principal_id, request["space_id"], page["id"]),
        ).fetchone()
        identical = c.execute(
            "SELECT * FROM assistant_wiki_proposals WHERE workspace_id=%s AND principal_id=%s AND space_id=%s AND kind='source_patch' AND target_page_id=%s AND input_fingerprint=%s",
            (
                self.workspace_id,
                self.principal_id,
                request["space_id"],
                page["id"],
                fingerprint,
            ),
        ).fetchone()
        if identical:
            return dict(identical)
        identity, now = f"wproposal_{uuid.uuid4().hex}", utc_now()
        proposal = dict(
            id=identity,
            kind="source_patch",
            target_page_id=page["id"],
            target_version=target_version,
            space_id=request["space_id"],
            payload_json=data,
            content_version=(previous["content_version"] + 1 if previous else 1),
            supersedes_id=(previous["id"] if previous else None),
            status="pending",
            created_at=now,
            updated_at=now,
        )
        self._validate_source_patch(c, proposal)
        self._expire_source_patches(c, page["id"])
        c.execute(
            "INSERT INTO assistant_wiki_proposals(workspace_id,principal_id,id,space_id,kind,target_page_id,target_version,input_fingerprint,payload_json,status,content_version,supersedes_id,created_at,updated_at) VALUES(%s,%s,%s,%s,'source_patch',%s,%s,%s,%s,'pending',%s,%s,%s,%s)",
            (
                self.workspace_id,
                self.principal_id,
                identity,
                request["space_id"],
                page["id"],
                target_version,
                fingerprint,
                Jsonb(data),
                proposal["content_version"],
                proposal["supersedes_id"],
                now,
                now,
            ),
        )
        self._notify_proposal(c, proposal)
        return proposal

    def _source_patch_view(self, c, proposal, *, prepared=None):
        metadata = {
            k: proposal.get(k)
            for k in (
                "id",
                "kind",
                "status",
                "content_version",
                "target_version",
                "supersedes_id",
                "decided_at",
                "created_at",
                "target_page_id",
                "space_id",
            )
        }
        try:
            # Reading never takes row locks or mutates status; validation uses
            # the same checks through a non-locking connection when requested.
            page = self._validate_source_patch(c, proposal, prepared=prepared)
        except (
            AssistantConflict,
            KeyError,
            ValueError,
            OSError,
            SourceChangedDuringCapture,
        ) as exc:
            return {**metadata, "confirmable": False, "reason": f"候选依据失效：{exc}"}
        data = proposal["payload_json"]
        baseline = self._visible_page(
            data["before"],
            conn=c,
            snapshot_cache=prepared
            if prepared is not None
            else self._notification_cache(c, page["id"]),
        )
        if data["request"].get("task_subset"):
            space = self.store.get_space(proposal["space_id"], conn=c)
            baseline = self._task_projection(
                baseline,
                self._scope({**space, "video_ids": data["request"]["task_subset"]}),
                conn=c,
            )
        return {
            **metadata,
            "confirmable": proposal["status"] == "pending",
            "before": baseline,
            "after": {"blocks": data["patch"]["blocks"]},
            "operation": data["patch"]["local_operation"],
            "origin_job_id": data["origin_job_id"],
            "video_id": data["video_id"],
            "revision": data["revision"],
        }

    def validate_source_proposal(self, identity, *, space_id):
        with self._transaction() as c:
            proposal = self._source_proposal(c, identity, space_id=space_id)
            if proposal["kind"] != "source_patch":
                raise AssistantConflict("wiki_proposal_kind")
            view = self._source_patch_view(c, proposal)
            if proposal["status"] == "pending" and not view["confirmable"]:
                c.execute(
                    "UPDATE assistant_wiki_proposals SET payload_json=jsonb_set(payload_json,'{decision_reason}',%s) WHERE workspace_id=%s AND id=%s",
                    (Jsonb(view["reason"]), self.workspace_id, identity),
                )
                c.execute(
                    "UPDATE assistant_wiki_proposals SET status='stale',decided_at=clock_timestamp(),updated_at=clock_timestamp() WHERE workspace_id=%s AND id=%s AND status='pending'",
                    (self.workspace_id, identity),
                )
                view["status"] = "stale"
            return view

    def _decide_source_patch(
        self,
        original,
        *,
        accept,
        operation_key,
        expected_content_version,
        expected_target_version,
        conn=None,
    ):
        stale = False
        prepared = None
        evidence_error = False
        if accept and original["status"] == "pending":
            try:
                prepared = self._source_patch_evidence(original)
            except (
                AssistantConflict,
                KeyError,
                ValueError,
                OSError,
                SourceChangedDuringCapture,
            ):
                evidence_error = True
        with self._transaction(
            conn, operation_key=operation_key, page_ids=(original["target_page_id"],)
        ) as c:
            proposal = self._source_proposal(
                c, original["id"], space_id=original["space_id"]
            )
            if (
                expected_content_version != proposal["content_version"]
                or expected_target_version != proposal["target_version"]
            ):
                raise AssistantConflict("wiki_proposal_review_version_conflict")
            receipt = c.execute(
                "SELECT result_json FROM assistant_mutation_receipts WHERE workspace_id=%s AND principal_id=%s AND operation_key=%s",
                (self.workspace_id, self.principal_id, operation_key),
            ).fetchone()
            if receipt:
                if receipt["result_json"].get("proposal_id") != proposal["id"]:
                    raise AssistantConflict("operation_key_conflict")
                return receipt["result_json"]
            if proposal["status"] != "pending":
                return {"proposal_id": proposal["id"], "status": proposal["status"]}
            if accept:
                view = (
                    {"confirmable": False}
                    if evidence_error
                    else self._source_patch_view(c, proposal, prepared=prepared)
                )
                if not view["confirmable"]:
                    stale = True
                    result = {"proposal_id": proposal["id"], "status": "stale"}
                else:
                    d = proposal["payload_json"]
                    page = self._publish_source_patch(
                        c,
                        space_id=proposal["space_id"],
                        video_id=d["video_id"],
                        revision=d["revision"],
                        expected_version=proposal["target_version"],
                        patch=d["patch"],
                        scope_version=d["scope_version"],
                        proposal=proposal,
                    )
                    result = {
                        "proposal_id": proposal["id"],
                        "status": "accepted",
                        "page_id": page["id"],
                        "version": page["version"],
                    }
            else:
                result = {"proposal_id": proposal["id"], "status": "rejected"}
            if stale:
                c.execute(
                    "UPDATE assistant_wiki_proposals SET payload_json=jsonb_set(payload_json,'{decision_reason}',%s) WHERE workspace_id=%s AND id=%s",
                    (Jsonb("review_basis_changed"), self.workspace_id, proposal["id"]),
                )
            c.execute(
                "UPDATE assistant_wiki_proposals SET status=%s,decided_at=clock_timestamp(),updated_at=clock_timestamp() WHERE workspace_id=%s AND id=%s AND status='pending'",
                (result["status"], self.workspace_id, proposal["id"]),
            )
            identity = self._notify_proposal(c, proposal)
            c.execute(
                "UPDATE assistant_notifications SET activity_at=clock_timestamp() WHERE workspace_id=%s AND principal_id=%s AND id=%s",
                (self.workspace_id, self.principal_id, identity),
            )
            if not stale:
                c.execute(
                    "INSERT INTO assistant_mutation_receipts(workspace_id,principal_id,operation_key,operation,result_json,created_at) VALUES(%s,%s,%s,'wiki_proposal_decision',%s,clock_timestamp())",
                    (
                        self.workspace_id,
                        self.principal_id,
                        operation_key,
                        Jsonb(result),
                    ),
                )
        if stale:
            raise AssistantConflict("wiki_proposal_stale")
        return result

    def refresh_source_proposal(self, identity, *, space_id, request_key):
        with self.db.connect(read_only=True) as c:
            proposal = self._source_proposal(c, identity, space_id=space_id)
            if proposal["kind"] != "source_patch":
                raise AssistantConflict("wiki_proposal_kind")
            data = proposal["payload_json"]
            space = self.store.get_space(space_id, conn=c)
            allowed = set(self.sources.visible_video_ids(self._scope(space), conn=c))
            if data["request"].get("task_subset"):
                allowed.intersection_update(data["request"]["task_subset"])
            vids = {data["video_id"]}
            if not vids.issubset(allowed):
                raise AssistantConflict("wiki_source_out_of_scope")
            refs = [f"video:{v}" for v in sorted(vids)]
        return self.request_topic(
            space_id=space_id,
            topic=data["patch"]["title"],
            source_refs=refs,
            request_key=request_key,
            task_subset=data["request"].get("task_subset"),
            review_proposal_id=identity,
        )

    def apply_patch(
        self,
        *,
        space_id: int,
        video_id: int,
        revision: str,
        expected_version: int,
        patch: dict[str, Any],
        scope_version: int,
        job_id: str,
        lease_owner: str,
        lease_epoch: int,
        conn=None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self._transaction(
            conn, job_claim=(job_id, lease_owner, lease_epoch)
        ) as connection:
            self._require_publish_allowed(connection=connection, conn=connection)
            self._validate_wiki_commit_fence(
                connection,
                space_id=space_id,
                video_id=video_id,
                revision=revision,
                scope_version=scope_version,
                job_id=job_id,
                lease_owner=lease_owner,
                lease_epoch=lease_epoch,
                now=now,
                conn=connection,
            )
            job = connection.execute(
                "SELECT payload_json FROM assistant_jobs WHERE workspace_id=%s AND principal_id=%s AND id=%s",
                (self.workspace_id, self.principal_id, job_id),
            ).fetchone()
            payload = job["payload_json"]
            direct = self._source_direct_authorized(connection, payload)
            if not direct and patch.get("local_operation") != "associate":
                if (
                    patch.get("local_operation") not in {"add_block", "revise_block"}
                    or expected_version == 0
                ):
                    raise AssistantConflict("unattended_wiki_requires_local_patch")
                proposal = self._create_source_patch(
                    connection, payload, patch, expected_version, job_id
                )
                job_transition(
                    connection,
                    self.db.context,
                    job_id,
                    lease_owner,
                    lease_epoch,
                    action="complete",
                )
                return {"proposal_id": proposal["id"], "status": proposal["status"]}
            page = self._publish_source_patch(
                connection,
                space_id=space_id,
                video_id=video_id,
                revision=revision,
                expected_version=expected_version,
                patch=patch,
                scope_version=scope_version,
                job_id=job_id,
            )
            page_id = page["id"]
            job_transition(
                connection,
                self.db.context,
                job_id,
                lease_owner,
                lease_epoch,
                action="complete",
            )
        return self.get_page(page_id, space_id=space_id, include_hidden=True, conn=conn)

    def _publish_source_patch(
        self,
        connection,
        *,
        space_id,
        video_id,
        revision,
        expected_version,
        patch,
        scope_version,
        job_id=None,
        proposal=None,
    ):
        """Domain writer shared by fenced Jobs and reviewed user commands."""
        now = utc_now()
        normalized = self._normalize_title(str(patch["title"]))
        space_row = connection.execute(
            "SELECT source_ids_json,video_ids_json,all_active FROM assistant_spaces WHERE assistant_spaces.workspace_id=%s AND id=%s",
            (
                self.workspace_id,
                space_id,
            ),
        ).fetchone()
        selected_videos = {int(value) for value in (space_row["video_ids_json"] or [])}
        selected_sources = {
            int(value) for value in (space_row["source_ids_json"] or [])
        }
        row = connection.execute(
            """
            SELECT * FROM assistant_wiki_pages
            WHERE assistant_wiki_pages.workspace_id=%s AND principal_id=%s AND space_id=%s AND normalized_title=%s
            """,
            (
                self.workspace_id,
                self.principal_id,
                space_id,
                normalized,
            ),
        ).fetchone()
        before_state = (
            self._operation_state(connection, str(row["id"]), conn=connection)
            if row
            else None
        )
        if row is None:
            if expected_version != 0:
                raise AssistantConflict("wiki_page_missing")
            page_id = f"awiki_{uuid.uuid4().hex}"
            blocks = self._blocks_with_identity(
                patch["blocks"], revision=revision, topic=patch["title"]
            )
            incoming_ids = {block["stable_id"] for block in blocks}
            connection.execute(
                """
                INSERT INTO assistant_wiki_pages(workspace_id,
                    id, principal_id, space_id, normalized_title, title, aliases_json,
                    page_type, summary, blocks_json, version, status, scope_version,
                    created_at, updated_at
                ) VALUES(%s,%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, 'active', %s, %s, %s)
                """,
                (
                    self.workspace_id,
                    page_id,
                    self.principal_id,
                    space_id,
                    normalized,
                    patch["title"],
                    Jsonb(patch.get("aliases", [])),
                    patch["page_type"],
                    patch["summary"],
                    Jsonb(blocks),
                    scope_version,
                    now,
                    now,
                ),
            )
            version = 1
            before = None
            operation = "created"
        else:
            current = self._decode_page(dict(row))
            self._assert_lifecycle(
                current,
                patch["blocks"],
                target_id=str(patch.get("target_block_id") or ""),
            )
            if int(current["version"]) != expected_version:
                raise AssistantConflict("wiki_version_conflict")
            page_id = str(current["id"])
            blocks = list(current["blocks"])
            local_operation = str(patch.get("local_operation") or "")
            target_id = str(patch.get("target_block_id") or "")
            if local_operation == "revise_block":
                target = next(
                    (item for item in blocks if item["stable_id"] == target_id),
                    None,
                )
                if target is None or target.get("manual_lock"):
                    raise AssistantConflict("wiki_manual_conflict")
                incoming_refs = {
                    str(ref)
                    for item in patch["blocks"]
                    for ref in item.get("source_refs", [])
                }
                valid_refs = set(
                    self._current_page_source_revisions(
                        page_id,
                        space=self.store.get_space(space_id, conn=connection),
                        conn=connection,
                    )
                )
                if (
                    not set(target.get("source_refs", []))
                    .intersection(valid_refs)
                    .issubset(incoming_refs)
                ):
                    raise AssistantConflict("proposal_missing_source_coverage")
            if patch.get("replace_derived"):
                covered = {
                    str(ref)
                    for block in patch["blocks"]
                    for ref in block.get("source_refs", [])
                }
                active_refs = {
                    str(item["source_revision"])
                    for item in connection.execute(
                        """SELECT DISTINCT d.source_revision, d.video_id, m.source_id
                        FROM assistant_wiki_dependencies d
                        JOIN assistant_source_heads h ON h.video_id=d.video_id
                          AND h.principal_id=%s AND h.current_revision=d.source_revision
                        JOIN video_source_memberships m ON m.video_id=d.video_id AND m.removed_at IS NULL
                        JOIN favorite_sources s ON s.id=m.source_id AND s.status='active'
                        JOIN videos v ON v.id=d.video_id AND NOT v.is_ignored AND v.archived_at IS NULL
                        WHERE d.workspace_id=%s AND d.page_id=%s AND d.block_id NOT IN (SELECT value->>'stable_id' FROM assistant_wiki_pages p,jsonb_array_elements(p.blocks_json) AS b(value) WHERE p.id=d.page_id AND coalesce((value->>'deleted')::boolean,false))""",
                        (
                            self.principal_id,
                            self.workspace_id,
                            page_id,
                        ),
                    ).fetchall()
                    if (not selected_videos or int(item["video_id"]) in selected_videos)
                    and (
                        bool(space_row["all_active"])
                        or int(item["source_id"]) in selected_sources
                    )
                }
                if not active_refs.issubset(covered) or revision not in covered:
                    raise AssistantConflict("proposal_missing_source_coverage")
            prior_ids = {
                str(item["block_id"])
                for item in connection.execute(
                    """
                    SELECT block_id FROM assistant_wiki_dependencies
                    WHERE assistant_wiki_dependencies.workspace_id=%s AND page_id=%s AND video_id=%s AND source_revision<>%s
                    """,
                    (
                        self.workspace_id,
                        page_id,
                        video_id,
                        revision,
                    ),
                ).fetchall()
            }
            replace_ids = {
                block["stable_id"]
                for block in blocks
                if not block.get("manual_lock")
                and not block.get("deleted")
                and (
                    (
                        local_operation == "revise_block"
                        and block["stable_id"] == target_id
                    )
                    or (not local_operation and bool(patch.get("replace_derived")))
                    or (not local_operation and block["stable_id"] in prior_ids)
                    or (
                        not local_operation
                        and revision in block.get("source_refs", [])
                        and block.get("compiler_version") != self.COMPILER_VERSION
                    )
                )
            }
            if replace_ids:
                blocks = [
                    block for block in blocks if block["stable_id"] not in replace_ids
                ]
                placeholders = ",".join("%s" for _ in replace_ids)
                connection.execute(
                    f"DELETE FROM assistant_wiki_dependencies WHERE assistant_wiki_dependencies.workspace_id=%s AND page_id=%s AND block_id IN ({placeholders})",
                    (
                        self.workspace_id,
                        page_id,
                        *sorted(replace_ids),
                    ),
                )
            incoming = self._blocks_with_identity(
                patch["blocks"], revision=revision, topic=patch["title"]
            )
            deleted_ids = {b["stable_id"] for b in self._deleted_blocks(current)}
            for block in incoming:
                if block["stable_id"] in deleted_ids:
                    # The ordinary generated ID uses position/revision, not text. Distinct new
                    # content needs its own identity; the tombstone itself remains untouched.
                    block["stable_id"] = (
                        "wblock_"
                        + hashlib.sha256(
                            f"{block['stable_id']}:{block['heading']}:{block['markdown']}".encode()
                        ).hexdigest()[:20]
                    )
            self._assert_lifecycle(current, incoming, target_id=target_id)
            incoming_ids = {block["stable_id"] for block in incoming}
            blocks.extend(
                block
                for block in incoming
                if block["stable_id"] not in {b["stable_id"] for b in blocks}
            )
            if local_operation in {"add_block", "revise_block"}:
                retained = {
                    str(ref) for block in blocks for ref in block.get("source_refs", [])
                }
                active_refs = set(
                    self._current_page_source_revisions(
                        page_id,
                        space=self.store.get_space(space_id, conn=connection),
                        conn=connection,
                    )
                )
                if not active_refs.issubset(retained) or revision not in retained:
                    raise AssistantConflict("proposal_missing_source_coverage")
            version = expected_version + 1
            before = current
            operation = (
                "source_amended"
                if replace_ids
                else (
                    "source_associated"
                    if local_operation == "associate"
                    else "source_integrated"
                )
            )
            aliases = list(
                dict.fromkeys(
                    [
                        *current["aliases"],
                        *[
                            str(value)
                            for value in patch.get("aliases", [])
                            if str(value).strip()
                        ],
                    ]
                )
            )[:24]
            updated = connection.execute(
                """
                UPDATE assistant_wiki_pages SET summary=%s, blocks_json=%s, aliases_json=%s, page_type=%s,
                    version=%s, scope_version=%s, status='active', updated_at=%s
                WHERE assistant_wiki_pages.workspace_id=%s AND id=%s AND version=%s
                """,
                (
                    self._pending_guide()
                    if any(b.get("deleted") for b in blocks)
                    else str(patch.get("summary") or current["summary"]),
                    Jsonb(blocks),
                    Jsonb(aliases),
                    patch["page_type"],
                    version,
                    scope_version,
                    now,
                    self.workspace_id,
                    page_id,
                    expected_version,
                ),
            )
            if updated.rowcount != 1:
                raise AssistantConflict("wiki_version_conflict")
        for block in blocks:
            if block["stable_id"] not in incoming_ids:
                continue
            for block_revision in block.get("source_refs", []):
                source_row = connection.execute(
                    """SELECT h.video_id FROM assistant_source_revisions r
                    JOIN assistant_source_heads h ON h.id=r.head_id
                    WHERE r.workspace_id=%s AND r.revision=%s AND h.principal_id=%s AND h.current_revision=%s""",
                    (
                        self.workspace_id,
                        block_revision,
                        self.principal_id,
                        block_revision,
                    ),
                ).fetchone()
                if source_row is None:
                    raise AssistantConflict("source_revision_changed")
                source_video_id = int(source_row["video_id"])
                if selected_videos and source_video_id not in selected_videos:
                    raise AssistantConflict("wiki_source_out_of_scope")
                memberships = connection.execute(
                    """SELECT m.source_id FROM video_source_memberships m
                    JOIN favorite_sources s ON s.id=m.source_id
                    JOIN videos v ON v.id=m.video_id
                    WHERE m.workspace_id=%s AND m.video_id=%s AND m.removed_at IS NULL AND s.status='active'
                      AND NOT v.is_ignored AND v.archived_at IS NULL""",
                    (
                        self.workspace_id,
                        source_video_id,
                    ),
                ).fetchall()
                if not any(
                    bool(space_row["all_active"])
                    or int(row["source_id"]) in selected_sources
                    for row in memberships
                ):
                    raise AssistantConflict("wiki_source_out_of_scope")
                connection.execute(
                    """INSERT INTO assistant_wiki_dependencies(workspace_id,
                        page_id, block_id, source_revision, video_id, dependency_kind, created_at
                    ) VALUES(%s,%s, %s, %s, %s, 'source', %s) ON CONFLICT DO NOTHING""",
                    (
                        self.workspace_id,
                        page_id,
                        block["stable_id"],
                        block_revision,
                        source_video_id,
                        now,
                    ),
                )
        relation = (
            "associated"
            if patch.get("local_operation") == "associate"
            else "supports_block"
        )
        connection.execute(
            """INSERT INTO assistant_wiki_materials(workspace_id,
                page_id,video_id,source_revision,relation,status,created_at,updated_at
            ) VALUES(%s,%s,%s,%s,%s,'integrated',%s,%s)
            ON CONFLICT(page_id,video_id) DO UPDATE SET
                source_revision=excluded.source_revision, relation=excluded.relation,
                status=excluded.status, updated_at=excluded.updated_at""",
            (
                self.workspace_id,
                page_id,
                video_id,
                revision,
                relation,
                now,
                now,
            ),
        )
        for block in blocks:
            for block_revision in block.get("source_refs", []):
                source = connection.execute(
                    "SELECT video_id FROM assistant_source_cards WHERE assistant_source_cards.workspace_id=%s AND revision=%s",
                    (
                        self.workspace_id,
                        block_revision,
                    ),
                ).fetchone()
                if source:
                    connection.execute(
                        """INSERT INTO assistant_wiki_materials(workspace_id,
                            page_id,video_id,source_revision,relation,status,created_at,updated_at
                        ) VALUES(%s,%s,%s,%s,'supports_block','integrated',%s,%s) ON CONFLICT DO NOTHING""",
                        (
                            self.workspace_id,
                            page_id,
                            int(source["video_id"]),
                            block_revision,
                            now,
                            now,
                        ),
                    )
        after_row = connection.execute(
            "SELECT * FROM assistant_wiki_pages WHERE assistant_wiki_pages.workspace_id=%s AND id=%s",
            (
                self.workspace_id,
                page_id,
            ),
        ).fetchone()
        after = self._decode_page(dict(after_row))
        self._record_notification_change(
            connection,
            """
            INSERT INTO assistant_wiki_changes(workspace_id,
                page_id, version, operation, before_json, after_json, summary, actor, created_at
            ) VALUES(%s,%s, %s, %s, %s, %s, %s, 'assistant', %s)
            """,
            (
                self.workspace_id,
                page_id,
                version,
                operation,
                Jsonb(before) if before else None,
                Jsonb(after),
                f"纳入来源：{patch.get('source_title') or revision[:8]}",
                now,
            ),
            proposal=proposal,
            cause={
                "job_id": job_id,
                "video_id": video_id,
                "snapshot_revision": revision,
            },
        )
        self._save_operation_state(
            connection, page_id, version, before_state, conn=connection
        )
        return {"id": page_id, "version": version}

    def _operation_state(
        self, connection: Any, page_id: str, *, conn=None
    ) -> dict[str, Any]:
        conn = connection if conn is None else conn
        row = connection.execute(
            "SELECT * FROM assistant_wiki_pages WHERE assistant_wiki_pages.workspace_id=%s AND id=%s",
            (
                self.workspace_id,
                page_id,
            ),
        ).fetchone()
        if row is None:
            raise KeyError(page_id)
        return {
            "page": self._decode_page(dict(row)),
            "sources": [
                dict(item)
                for item in connection.execute(
                    """SELECT block_id,source_revision,video_id,dependency_kind
                FROM assistant_wiki_dependencies WHERE assistant_wiki_dependencies.workspace_id=%s AND page_id=%s""",
                    (
                        self.workspace_id,
                        page_id,
                    ),
                ).fetchall()
            ],
            "personal": [
                dict(item)
                for item in connection.execute(
                    """SELECT block_id,memory_id,memory_version,source_message_id
                FROM assistant_wiki_personal_dependencies WHERE assistant_wiki_personal_dependencies.workspace_id=%s AND page_id=%s""",
                    (
                        self.workspace_id,
                        page_id,
                    ),
                ).fetchall()
            ],
            "materials": [
                dict(item)
                for item in connection.execute(
                    """SELECT video_id,source_revision,relation,status
                FROM assistant_wiki_materials WHERE assistant_wiki_materials.workspace_id=%s AND page_id=%s""",
                    (
                        self.workspace_id,
                        page_id,
                    ),
                ).fetchall()
            ],
            "redirects": [
                dict(item)
                for item in connection.execute(
                    "SELECT old_page_id FROM assistant_wiki_redirects WHERE assistant_wiki_redirects.workspace_id=%s AND target_page_id=%s",
                    (
                        self.workspace_id,
                        page_id,
                    ),
                ).fetchall()
            ],
        }

    def _save_operation_state(
        self,
        connection: Any,
        page_id: str,
        version: int,
        before: dict[str, Any] | None,
        *,
        conn=None,
    ) -> None:
        conn = connection if conn is None else conn
        connection.execute(
            "UPDATE workspace_guards SET dependency_epoch=dependency_epoch+1 WHERE workspace_id=%s",
            (self.workspace_id,),
        )
        after = self._operation_state(connection, page_id, conn=conn)
        connection.execute(
            """INSERT INTO assistant_wiki_operation_states(workspace_id,page_id,version,before_json,after_json)
            VALUES(%s,%s,%s,%s,%s)""",
            (
                self.workspace_id,
                page_id,
                version,
                Jsonb(before) if before else None,
                Jsonb(after),
            ),
        )

    def history_source_refs(
        self, page_id: str, *, space_id: int, conn=None
    ) -> list[str]:
        page = self.get_page(page_id, space_id=space_id, conn=conn)
        visible_blocks = {str(block["stable_id"]) for block in page["blocks"]}
        if not visible_blocks:
            return []
        placeholders = ",".join("%s" for _ in visible_blocks)
        with self.db.connect(conn) as connection:
            rows = connection.execute(
                f"\n                SELECT d.video_id, d.source_revision\n                FROM assistant_wiki_dependencies d\n                JOIN assistant_source_heads h ON h.video_id=d.video_id\n                    AND h.principal_id=%s AND h.current_revision=d.source_revision\n                WHERE d.workspace_id=%s AND d.page_id=%s AND d.block_id IN ({placeholders})\n                ",
                (
                    self.principal_id,
                    self.workspace_id,
                    page_id,
                    *sorted(visible_blocks),
                ),
            ).fetchall()
        refs: list[str] = []
        for row in rows:
            refs.append(f"video:{int(row['video_id'])}:{row['source_revision']}")
        if any(block.get("source_refs") for block in page["blocks"]) and not refs:
            raise ValueError("historical_result_dependencies_missing")
        return sorted(set(refs))

    def _current_page_source_revisions(
        self, page_id: str, *, space: dict[str, Any], conn=None
    ) -> list[str]:
        """Find current cards even when a mixed old/new block must be hidden."""
        visible_video_ids = set(
            self.sources.visible_video_ids(self._scope(space), conn=conn)
        )
        with self.db.connect(conn) as connection:
            rows = connection.execute(
                """SELECT DISTINCT d.video_id, d.source_revision
                FROM assistant_wiki_dependencies d
                JOIN assistant_source_heads h ON h.video_id=d.video_id
                  AND h.principal_id=%s AND h.current_revision=d.source_revision
                WHERE d.workspace_id=%s AND d.page_id=%s AND d.block_id NOT IN
                    (SELECT value->>'stable_id' FROM assistant_wiki_pages p,jsonb_array_elements(p.blocks_json) AS b(value) WHERE p.id=d.page_id AND coalesce((value->>'deleted')::boolean,false)) ORDER BY d.video_id, d.source_revision""",
                (
                    self.principal_id,
                    self.workspace_id,
                    page_id,
                ),
            ).fetchall()
        return [
            str(row["source_revision"])
            for row in rows
            if int(row["video_id"]) in visible_video_ids
        ]

    def _validate_wiki_commit_fence(
        self,
        connection: Any,
        *,
        space_id: int,
        video_id: int,
        revision: str,
        scope_version: int,
        job_id: str,
        lease_owner: str,
        lease_epoch: int,
        now: str,
        conn=None,
    ) -> None:
        conn = connection if conn is None else conn
        job, _ = guard_job(
            connection, self.db.context, job_id, lease_owner, lease_epoch
        )
        if job["kind"] != "wiki_integrate":
            raise AssistantConflict("wiki_job_lease_lost")
        job_payload = job["payload_json"] or {}
        self._require_maintenance_authorized(
            job_payload, connection=connection, conn=conn
        )
        if (
            int(job_payload.get("space_id") or 0) != space_id
            or int(job_payload.get("video_id") or 0) != video_id
            or str(job_payload.get("revision") or "") != revision
            or int(job_payload.get("scope_version") or 0) != scope_version
        ):
            raise AssistantConflict("wiki_job_payload_changed")
        source_message_id = str(job_payload.get("source_message_id") or "")
        if source_message_id:
            source_message = connection.execute(
                """SELECT m.id FROM assistant_messages m
                JOIN assistant_threads t ON t.id=m.thread_id
                WHERE m.workspace_id=%s AND m.id=%s AND m.role='user' AND t.space_id=%s AND t.principal_id=%s""",
                (
                    self.workspace_id,
                    source_message_id,
                    space_id,
                    self.principal_id,
                ),
            ).fetchone()
            if source_message is None:
                raise AssistantConflict("wiki_task_input_stale")
            suppressed = connection.execute(
                """SELECT source_message_ids_json FROM assistant_memory_suppressions
                WHERE assistant_memory_suppressions.workspace_id=%s AND principal_id=%s AND (scope_kind='user' OR (scope_kind='space' AND scope_id=%s))""",
                (
                    self.workspace_id,
                    self.principal_id,
                    str(space_id),
                ),
            ).fetchall()
            if any(
                source_message_id in (row["source_message_ids_json"] or [])
                for row in suppressed
            ):
                raise AssistantConflict("wiki_task_input_stale")
        self._validate_source_scope(connection, space_id=space_id, video_id=video_id,
                                    revision=revision, scope_version=scope_version)

    def _validate_source_scope(self, connection, *, space_id, video_id, revision, scope_version):
        space = connection.execute(
            """
            SELECT source_ids_json, video_ids_json, all_active, scope_version, enabled
            FROM assistant_spaces WHERE assistant_spaces.workspace_id=%s AND id=%s AND principal_id=%s
            """,
            (
                self.workspace_id,
                space_id,
                self.principal_id,
            ),
        ).fetchone()
        if (
            space is None
            or not bool(space["enabled"])
            or int(space["scope_version"]) != scope_version
        ):
            raise AssistantConflict("wiki_scope_changed")
        selected_sources = {int(value) for value in (space["source_ids_json"] or [])}
        selected_videos = {int(value) for value in (space["video_ids_json"] or [])}
        if selected_videos and video_id not in selected_videos:
            raise AssistantConflict("wiki_source_out_of_scope")
        membership_params: list[Any] = [video_id]
        source_clause = ""
        if not bool(space["all_active"]):
            if not selected_sources:
                raise AssistantConflict("wiki_source_out_of_scope")
            placeholders = ",".join("%s" for _ in selected_sources)
            source_clause = f" AND m.source_id IN ({placeholders})"
            membership_params.extend(sorted(selected_sources))
        visible = connection.execute(
            f"\n            SELECT 1 FROM video_source_memberships m\n            JOIN favorite_sources s ON s.id=m.source_id\n            JOIN videos v ON v.id=m.video_id\n            WHERE m.workspace_id=%s AND m.video_id=%s AND m.removed_at IS NULL AND s.status='active'\n              AND NOT v.is_ignored AND v.archived_at IS NULL {source_clause}\n            LIMIT 1\n            ",
            [*membership_params[:0], self.workspace_id, *membership_params[0:]],
        ).fetchone()
        if visible is None:
            raise AssistantConflict("wiki_source_out_of_scope")
        head = connection.execute(
            """
            SELECT current_revision FROM assistant_source_heads
            WHERE assistant_source_heads.workspace_id=%s AND principal_id=%s AND video_id=%s
            """,
            (
                self.workspace_id,
                self.principal_id,
                video_id,
            ),
        ).fetchone()
        if head is None or str(head["current_revision"] or "") != revision:
            raise AssistantConflict("source_revision_changed")

    def block_source_refs(
        self, blocks: list[dict[str, Any]], *, conn=None
    ) -> list[str]:
        refs = set()
        with self.db.connect(conn) as connection:
            for block in blocks:
                for value in block.get("source_refs") or []:
                    ref = str(value)
                    if ref.startswith("video:"):
                        refs.add(ref)
                        continue
                    # Wiki stores revision hashes; resolve existing storage
                    # relationships rather than treating them as scope-free.
                    row = connection.execute(
                        "SELECT h.video_id FROM assistant_source_revisions r JOIN assistant_source_heads h ON h.id=r.head_id WHERE r.workspace_id=%s AND r.revision=%s AND h.principal_id=%s",
                        (
                            self.workspace_id,
                            ref,
                            self.principal_id,
                        ),
                    ).fetchone()
                    if row is None:
                        return []
                    refs.add(f"video:{int(row['video_id'])}:{ref}")
        return sorted(refs)

    def _task_projection(
        self, page: dict[str, Any], scope: SourceScope | None, *, conn=None
    ) -> dict[str, Any]:
        if scope is None:
            return page
        blocks = []
        for block in page["blocks"]:
            refs = self.block_source_refs([block], conn=conn)
            if refs and self.sources.source_refs_visible(refs, scope, conn=conn):
                blocks.append({**block, "source_refs": refs})
        # Mixed/unknown blocks cannot be split into independently justified facts.
        allowed = set(self.sources.visible_video_ids(scope, conn=conn))
        materials = [
            item
            for item in page.get("materials") or []
            if int(item["video_id"]) in allowed
        ]
        complete = len(blocks) == len(page["blocks"]) and len(materials) == len(
            page.get("materials") or []
        )
        return {
            **page,
            "blocks": blocks,
            "summary": page.get("summary", "")
            if complete
            else "当前任务资料子集中的可用内容",
            "materials": materials,
            "availability": page.get("availability", "full") if complete else "partial",
            "task_projection": True,
        }

    @staticmethod
    def _deleted_blocks(page: dict) -> list[dict]:
        return [
            block
            for block in page["blocks"]
            if block.get("deleted") and not block.get("deletion_released")
        ]

    @classmethod
    def _assert_lifecycle(
        cls, page: dict, incoming: list[dict] = (), *, target_id: str = ""
    ) -> None:
        if page["status"] != "active":
            raise AssistantConflict("wiki_page_inactive")
        tombstones = cls._deleted_blocks(page)
        clean = lambda text: " ".join(str(text or "").split())
        for tomb in tombstones:
            ids = {
                value
                for value in (tomb["stable_id"], tomb.get("deleted_stable_id"))
                if value
            }
            if target_id and target_id in ids:
                raise AssistantConflict("wiki_block_deleted")
            for block in incoming:
                if block.get("stable_id") in ids or (
                    clean(block.get("heading")),
                    clean(block.get("markdown")),
                ) == (clean(tomb.get("heading")), clean(tomb.get("markdown"))):
                    raise AssistantConflict("wiki_deleted_content_conflict")

    def manage_page(
        self,
        page_id: str,
        *,
        space_id: int,
        action: str,
        expected_version: int,
        operation_key: str,
        block_id: str | None = None,
        conn=None,
        _notification_id=None,
    ) -> dict:
        """Explicit user lifecycle operation; deletion is logical and reversible."""
        if action not in {"delete_block", "restore_block", "archive", "restore"}:
            raise ValueError("invalid_wiki_action")
        self.store.get_space(space_id, conn=conn)
        with self._transaction(
            conn, operation_key=operation_key, page_ids=[page_id]
        ) as connection:
            row = connection.execute(
                "SELECT * FROM assistant_wiki_pages WHERE assistant_wiki_pages.workspace_id=%s AND id=%s AND principal_id=%s AND space_id=%s",
                (
                    self.workspace_id,
                    page_id,
                    self.principal_id,
                    space_id,
                ),
            ).fetchone()
            if row is None:
                raise KeyError(page_id)
            receipt = connection.execute(
                "SELECT result_json FROM assistant_mutation_receipts WHERE assistant_mutation_receipts.workspace_id=%s AND operation_key=%s AND principal_id=%s",
                (
                    self.workspace_id,
                    operation_key,
                    self.principal_id,
                ),
            ).fetchone()
            if receipt:
                result = receipt["result_json"]
                if (
                    result.get("page_id") != page_id
                    or result.get("action") != action
                    or result.get("block_id") != block_id
                ):
                    raise AssistantConflict("operation_key_conflict")
                return result
            before = self._decode_page(dict(row))
            if int(before["version"]) != expected_version:
                raise AssistantConflict("wiki_version_conflict")
            if before["status"] == "merged" or (
                before["status"] != "active" and action != "restore"
            ):
                raise AssistantConflict("wiki_page_inactive")
            if action == "restore" and before["status"] != "archived":
                raise AssistantConflict("wiki_page_not_archived")
            snapshot = self._operation_state(connection, page_id, conn=connection)
            blocks = before["blocks"]
            status = before["status"]
            if action in {"delete_block", "restore_block"}:
                block = next(
                    (block for block in blocks if block["stable_id"] == block_id), None
                )
                if block is None:
                    raise KeyError(block_id)
                if bool(block.get("deleted")) != (action == "restore_block"):
                    raise AssistantConflict("wiki_block_state_changed")
                if action == "delete_block":
                    block["lock_before_delete"] = bool(block.get("manual_lock"))
                    block.update(
                        deleted=True, manual_lock=True, deletion_released=False
                    )
                else:
                    block.update(
                        deleted=False,
                        manual_lock=bool(block.get("lock_before_delete")),
                        deletion_released=True,
                    )
                block["lifecycle_version"] = expected_version + 1
            else:
                status = "archived" if action == "archive" else "active"
            connection.execute(
                "UPDATE assistant_wiki_pages SET blocks_json=%s,status=%s,summary=%s,version=version+1,updated_at=%s WHERE assistant_wiki_pages.workspace_id=%s AND id=%s AND version=%s",
                (
                    Jsonb(blocks),
                    status,
                    self._pending_guide(),
                    utc_now(),
                    self.workspace_id,
                    page_id,
                    expected_version,
                ),
            )
            after = self._decode_page(
                dict(
                    connection.execute(
                        "SELECT * FROM assistant_wiki_pages WHERE assistant_wiki_pages.workspace_id=%s AND id=%s",
                        (
                            self.workspace_id,
                            page_id,
                        ),
                    ).fetchone()
                )
            )
            self._record_notification_change(
                connection,
                "INSERT INTO assistant_wiki_changes(workspace_id,page_id,version,operation,before_json,after_json,summary,actor,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,'user',%s)",
                (
                    self.workspace_id,
                    page_id,
                    expected_version + 1,
                    action,
                    Jsonb(snapshot["page"]),
                    Jsonb(after),
                    "可撤销逻辑删除" if action == "delete_block" else action,
                    utc_now(),
                ),
                cause={"operation_key": operation_key},
                undo_id=_notification_id,
            )
            self._save_operation_state(
                connection, page_id, expected_version + 1, snapshot, conn=connection
            )
            result = {
                "page_id": page_id,
                "version": expected_version + 1,
                "action": action,
                "block_id": block_id,
                "status": status,
            }
            connection.execute(
                "INSERT INTO assistant_mutation_receipts(workspace_id,operation_key,principal_id,operation,result_json,created_at) VALUES(%s,%s,%s,'wiki_lifecycle',%s,%s)",
                (
                    self.workspace_id,
                    operation_key,
                    self.principal_id,
                    Jsonb(result),
                    utc_now(),
                ),
            )
            return result

    def management_page(
        self,
        page_id: str,
        *,
        space_id: int,
        task_scope: SourceScope | None = None,
        conn=None,
        prepared_sources=None,
    ) -> dict:
        # Management retains deleted identities, never returns their body as normal evidence.
        if prepared_sources is None:
            prepared_sources = (
                self._prepare_sources_for_write(space_id=space_id)
                if conn is None
                else {}
            )
        raw = self.get_page(
            page_id,
            space_id=space_id,
            include_hidden=True,
            conn=conn,
            prepared_sources=prepared_sources,
        )
        visible = self._task_projection(
            self._visible_page(raw, conn=conn, snapshot_cache=prepared_sources),
            task_scope,
            conn=conn,
        )
        allowed_deleted = self._task_projection(
            {**raw, "blocks": [b for b in raw["blocks"] if b.get("deleted")]},
            task_scope,
            conn=conn,
        )["blocks"]
        return {
            **visible,
            "deleted_blocks": [
                {"stable_id": b["stable_id"], "heading": b["heading"]}
                for b in allowed_deleted
            ],
        }

    def list_pages(
        self,
        *,
        space_id: int,
        query: str = "",
        task_scope: SourceScope | None = None,
        conn=None,
        prepared_sources=None,
    ) -> list[dict[str, Any]]:
        from shiliu.assistant.wiki_projection import WikiProjection

        if prepared_sources is None:
            prepared_sources = (
                self._prepare_sources_for_write(space_id=space_id)
                if conn is None
                else {}
            )
        snapshot = WikiProjection(self).capture(
            space_id, scope=task_scope, conn=conn, prepared=prepared_sources
        )
        tokens = self._topic_tokens(query) if query.strip() else set()
        values = []
        for page in snapshot["pages"]:
            if not page["blocks"]:
                continue
            searchable = " ".join(
                [
                    page["title"],
                    page["summary"],
                    *[f"{b['heading']} {b['markdown']}" for b in page["blocks"]],
                ]
            )
            score = len(tokens & self._topic_tokens(searchable)) if tokens else 0
            if tokens and score == 0:
                continue
            values.append((score, page))
        values.sort(key=lambda item: (item[0], item[1]["updated_at"]), reverse=True)
        return [page for _, page in values]

    def get_page(
        self,
        page_id: str,
        *,
        space_id: int | None = None,
        include_hidden: bool = False,
        task_scope: SourceScope | None = None,
        conn=None,
        prepared_sources=None,
    ) -> dict[str, Any]:
        if prepared_sources is None:
            prepared_sources = (
                self._prepare_sources_for_write(space_id=space_id, page_id=page_id)
                if conn is None
                else {}
            )
        with self.db.connect(conn) as connection:
            row = connection.execute(
                "SELECT * FROM assistant_wiki_pages WHERE assistant_wiki_pages.workspace_id=%s AND id=%s AND principal_id=%s",
                (
                    self.workspace_id,
                    page_id,
                    self.principal_id,
                ),
            ).fetchone()
            redirect = connection.execute(
                "SELECT target_page_id,space_id FROM assistant_wiki_redirects WHERE assistant_wiki_redirects.workspace_id=%s AND old_page_id=%s",
                (
                    self.workspace_id,
                    page_id,
                ),
            ).fetchone()
        if row is None:
            raise KeyError(page_id)
        page = self._decode_page(dict(row))
        if space_id is not None and int(page["space_id"]) != int(space_id):
            raise KeyError(page_id)
        if page["status"] == "merged" and redirect is not None:
            if int(redirect["space_id"]) != int(page["space_id"]):
                raise KeyError(page_id)
            target = self.get_page(
                str(redirect["target_page_id"]),
                space_id=int(page["space_id"]),
                task_scope=task_scope,
                conn=conn,
                prepared_sources=prepared_sources,
            )
            return {**target, "redirected_from": page_id}
        if page["status"] != "active" and not include_hidden:
            raise KeyError(page_id)
        if include_hidden:
            return page
        from shiliu.assistant.wiki_projection import WikiProjection

        projected = WikiProjection(self).capture(
            int(page["space_id"]),
            scope=task_scope,
            page_id=page["id"],
            conn=conn,
            prepared=prepared_sources,
        )
        return (
            projected["pages"][0]
            if projected["pages"]
            else {
                **page,
                "blocks": [],
                "summary": "暂无当前可用的主题正文。",
                "availability": "partial",
            }
        )

    def edit_block(
        self,
        page_id: str,
        *,
        block_id: str,
        markdown: str,
        expected_version: int,
        operation_key: str,
        conn=None,
        prepared_sources=None,
    ) -> dict[str, Any]:
        if prepared_sources is None:
            prepared_sources = (
                self._prepare_sources_for_write(page_id=page_id) if conn is None else {}
            )
        clean = markdown.strip()
        if not clean or len(clean) > 20000:
            raise ValueError("invalid_wiki_block")
        now = utc_now()
        with self._transaction(
            conn, operation_key=operation_key, page_ids=[page_id]
        ) as connection:
            receipt = connection.execute(
                "SELECT result_json FROM assistant_mutation_receipts WHERE assistant_mutation_receipts.workspace_id=%s AND operation_key=%s AND principal_id=%s",
                (
                    self.workspace_id,
                    operation_key,
                    self.principal_id,
                ),
            ).fetchone()
            if receipt is not None:
                return receipt["result_json"]
            row = connection.execute(
                "SELECT * FROM assistant_wiki_pages WHERE assistant_wiki_pages.workspace_id=%s AND id=%s AND principal_id=%s",
                (
                    self.workspace_id,
                    page_id,
                    self.principal_id,
                ),
            ).fetchone()
            if row is None:
                raise KeyError(page_id)
            before = self._decode_page(dict(row))
            before_state = self._operation_state(connection, page_id, conn=connection)
            if int(before["version"]) != expected_version:
                raise AssistantConflict("wiki_version_conflict")
            self._assert_lifecycle(before, target_id=block_id)
            blocks = list(before["blocks"])
            target = next(
                (block for block in blocks if block["stable_id"] == block_id), None
            )
            if target is None:
                raise KeyError(block_id)
            target["markdown"] = clean
            target["manual_lock"] = True
            version = expected_version + 1
            updated = connection.execute(
                """
                UPDATE assistant_wiki_pages SET blocks_json=%s, summary=%s, version=%s, updated_at=%s
                WHERE assistant_wiki_pages.workspace_id=%s AND id=%s AND version=%s
                """,
                (
                    Jsonb(blocks),
                    self._pending_guide(),
                    version,
                    now,
                    self.workspace_id,
                    page_id,
                    expected_version,
                ),
            )
            if updated.rowcount != 1:
                raise AssistantConflict("wiki_version_conflict")
            after = self._decode_page(
                dict(
                    connection.execute(
                        "SELECT * FROM assistant_wiki_pages WHERE assistant_wiki_pages.workspace_id=%s AND id=%s",
                        (
                            self.workspace_id,
                            page_id,
                        ),
                    ).fetchone()
                )
            )
            self._record_notification_change(
                connection,
                """
                INSERT INTO assistant_wiki_changes(workspace_id,
                    page_id, version, operation, before_json, after_json, summary, actor, created_at
                ) VALUES(%s,%s, %s, 'block_edited', %s, %s, '人工编辑知识块', 'user', %s)
                """,
                (
                    self.workspace_id,
                    page_id,
                    version,
                    Jsonb(before),
                    Jsonb(after),
                    now,
                ),
                cause={"operation_key": operation_key},
            )
            self._save_operation_state(
                connection, page_id, version, before_state, conn=connection
            )
            connection.execute(
                """
                INSERT INTO assistant_mutation_receipts(workspace_id,
                    operation_key, principal_id, operation, result_json, created_at
                ) VALUES(%s,%s, %s, 'wiki_edit', %s, %s)
                """,
                (
                    self.workspace_id,
                    operation_key,
                    self.principal_id,
                    Jsonb(after),
                    now,
                ),
            )
        return self._visible_page(after, conn=conn, snapshot_cache=prepared_sources)

    def revise_derived_blocks(
        self,
        page_id: str,
        *,
        space_id: int,
        expected_version: int,
        edits: list[dict[str, str]],
        summary: str,
        operation_key: str,
        conn=None,
        prepared_sources=None,
    ) -> dict[str, Any]:
        """Traceable, bounded repair of selected generated blocks; never edit manual notes."""
        if prepared_sources is None:
            prepared_sources = (
                self._prepare_sources_for_write(space_id=space_id)
                if conn is None
                else {}
            )
        if not 1 <= len(edits) <= 4 or not 1 <= len(summary) <= 3000:
            raise ValueError("invalid_derived_revision")
        now = utc_now()
        with self._transaction(
            conn, operation_key=operation_key, page_ids=[page_id]
        ) as connection:
            receipt = connection.execute(
                "SELECT result_json FROM assistant_mutation_receipts WHERE assistant_mutation_receipts.workspace_id=%s AND operation_key=%s AND principal_id=%s",
                (
                    self.workspace_id,
                    operation_key,
                    self.principal_id,
                ),
            ).fetchone()
            if receipt:
                return self._visible_page(
                    (receipt["result_json"]),
                    conn=connection,
                    snapshot_cache=prepared_sources,
                )
            row = connection.execute(
                """SELECT * FROM assistant_wiki_pages WHERE assistant_wiki_pages.workspace_id=%s AND id=%s AND principal_id=%s AND space_id=%s
                AND status='active'""",
                (
                    self.workspace_id,
                    page_id,
                    self.principal_id,
                    space_id,
                ),
            ).fetchone()
            if row is None:
                raise KeyError(page_id)
            before = self._decode_page(dict(row))
            if int(before["version"]) != expected_version:
                raise AssistantConflict("wiki_version_conflict")
            before_state = self._operation_state(connection, page_id, conn=connection)
            blocks = list(before["blocks"])
            seen = set()
            source_replacements: list[tuple[str, list[tuple[int, str]]]] = []
            for edit in edits:
                block_id = edit.get("block_id")
                self._assert_lifecycle(before, target_id=block_id)
                if block_id in seen:
                    raise ValueError("duplicate_block_edit")
                seen.add(block_id)
                target = next(
                    (item for item in blocks if item["stable_id"] == block_id), None
                )
                discussion_role_fix = bool(
                    target
                    and target.get("user_input_source") == "discussion"
                    and edit.get("assessment") == "system_synthesis"
                )
                if target is None or (
                    (
                        target.get("manual_lock")
                        or target.get("assessment") == "user_explicit"
                    )
                    and not discussion_role_fix
                ):
                    raise AssistantConflict("wiki_manual_conflict")
                heading, body = (
                    str(edit.get("heading") or "").strip(),
                    str(edit.get("markdown") or "").strip(),
                )
                if not heading or not body or len(heading) > 160 or len(body) > 12000:
                    raise ValueError("invalid_derived_revision")
                target["heading"], target["markdown"] = heading, body
                if "applicability" in edit:
                    target["applicability"] = str(edit["applicability"]).strip()[:600]
                if "assessment" in edit:
                    if edit["assessment"] not in {
                        "source_reported",
                        "system_synthesis",
                    }:
                        raise ValueError("invalid_derived_role")
                    target["assessment"] = edit["assessment"]
                    if discussion_role_fix:
                        target["manual_lock"] = False
                        target["relation"] = "discussion_analysis"
                        target.pop("user_quote", None)
                if "source_refs" in edit:
                    if target.get("assessment") == "user_explicit":
                        raise ValueError("personal_block_source_conflict")
                    resolved = []
                    for ref in list(dict.fromkeys(edit["source_refs"])):
                        parts = str(ref).split(":")
                        if (
                            len(parts) != 3
                            or parts[0] != "video"
                            or not parts[1].isdigit()
                        ):
                            raise ValueError("versioned_video_source_required")
                        video_id, revision = int(parts[1]), parts[2]
                        head = connection.execute(
                            "SELECT current_revision FROM assistant_source_heads WHERE assistant_source_heads.workspace_id=%s AND principal_id=%s AND video_id=%s",
                            (
                                self.workspace_id,
                                self.principal_id,
                                video_id,
                            ),
                        ).fetchone()
                        if head is None or str(head["current_revision"]) != revision:
                            raise AssistantConflict("source_revision_changed")
                        if video_id not in self.sources.visible_video_ids(
                            self._scope(
                                self.store.get_space(space_id, conn=connection)
                            ),
                            conn=conn,
                        ):
                            raise AssistantConflict("wiki_source_out_of_scope")
                        resolved.append((video_id, revision))
                    target["source_refs"] = [revision for _, revision in resolved]
                    source_replacements.append((block_id, resolved))
            for block_id, resolved in source_replacements:
                connection.execute(
                    "DELETE FROM assistant_wiki_dependencies WHERE assistant_wiki_dependencies.workspace_id=%s AND page_id=%s AND block_id=%s",
                    (
                        self.workspace_id,
                        page_id,
                        block_id,
                    ),
                )
                for video_id, revision in resolved:
                    connection.execute(
                        """INSERT INTO assistant_wiki_dependencies(workspace_id,page_id,block_id,source_revision,video_id,
                        dependency_kind,created_at) VALUES(%s,%s,%s,%s,%s,'source',%s)""",
                        (
                            self.workspace_id,
                            page_id,
                            block_id,
                            revision,
                            video_id,
                            now,
                        ),
                    )
            if source_replacements:
                connection.execute(
                    """UPDATE assistant_wiki_materials SET relation='associated',updated_at=%s
                    WHERE assistant_wiki_materials.workspace_id=%s AND page_id=%s AND video_id NOT IN
                    (SELECT DISTINCT video_id FROM assistant_wiki_dependencies WHERE page_id=%s)""",
                    (
                        now,
                        self.workspace_id,
                        page_id,
                        page_id,
                    ),
                )
            version = expected_version + 1
            connection.execute(
                """UPDATE assistant_wiki_pages SET summary=%s,blocks_json=%s,version=%s,updated_at=%s
                WHERE assistant_wiki_pages.workspace_id=%s AND id=%s AND version=%s""",
                (
                    summary,
                    Jsonb(blocks),
                    version,
                    now,
                    self.workspace_id,
                    page_id,
                    expected_version,
                ),
            )
            after = self._decode_page(
                dict(
                    connection.execute(
                        "SELECT * FROM assistant_wiki_pages WHERE assistant_wiki_pages.workspace_id=%s AND id=%s",
                        (
                            self.workspace_id,
                            page_id,
                        ),
                    ).fetchone()
                )
            )
            self._record_notification_change(
                connection,
                """INSERT INTO assistant_wiki_changes(workspace_id,page_id,version,operation,before_json,after_json,
                summary,actor,created_at) VALUES(%s,%s,%s,'derived_repair',%s,%s,%s,'assistant',%s)""",
                (
                    self.workspace_id,
                    page_id,
                    version,
                    Jsonb(before),
                    Jsonb(after),
                    "定点修正生成内容",
                    now,
                ),
                cause={"operation_key": operation_key},
            )
            self._save_operation_state(
                connection, page_id, version, before_state, conn=connection
            )
            connection.execute(
                """INSERT INTO assistant_mutation_receipts(workspace_id,operation_key,principal_id,operation,result_json,created_at)
                VALUES(%s,%s,%s,'wiki_derived_repair',%s,%s)""",
                (
                    self.workspace_id,
                    operation_key,
                    self.principal_id,
                    Jsonb(after),
                    now,
                ),
            )
        return self._visible_page(after, conn=conn, snapshot_cache=prepared_sources)

    def add_personal_note(
        self,
        page_id: str,
        *,
        space_id: int,
        text: str,
        expected_version: int,
        operation_key: str,
        memory_id: str | None = None,
        memory_version: int | None = None,
        source_message_id: str | None = None,
        conn=None,
        prepared_sources=None,
    ) -> dict[str, Any]:
        if prepared_sources is None:
            prepared_sources = (
                self._prepare_sources_for_write(space_id=space_id)
                if conn is None
                else {}
            )
        clean = text.strip()
        if not clean or len(clean) > 4000:
            raise ValueError("invalid_personal_note")
        now = utc_now()
        if bool(memory_id) != (memory_version is not None):
            raise ValueError("memory_dependency_required")
        with self._transaction(
            conn, operation_key=operation_key, page_ids=[page_id]
        ) as connection:
            receipt = connection.execute(
                "SELECT result_json FROM assistant_mutation_receipts WHERE assistant_mutation_receipts.workspace_id=%s AND operation_key=%s AND principal_id=%s",
                (
                    self.workspace_id,
                    operation_key,
                    self.principal_id,
                ),
            ).fetchone()
            if receipt is not None:
                return self._visible_page(
                    (receipt["result_json"]),
                    conn=connection,
                    snapshot_cache=prepared_sources,
                )
            row = connection.execute(
                "SELECT * FROM assistant_wiki_pages WHERE assistant_wiki_pages.workspace_id=%s AND id=%s AND principal_id=%s AND space_id=%s AND status='active'",
                (
                    self.workspace_id,
                    page_id,
                    self.principal_id,
                    space_id,
                ),
            ).fetchone()
            if row is None:
                raise KeyError(page_id)
            before = self._decode_page(dict(row))
            before_state = self._operation_state(connection, page_id, conn=connection)
            if int(before["version"]) != expected_version:
                raise AssistantConflict("wiki_version_conflict")
            if memory_id and not self._personal_dependency_current(
                connection,
                space_id=space_id,
                memory_id=memory_id,
                memory_version=int(memory_version),
                source_message_id=source_message_id,
                conn=connection,
            ):
                raise AssistantConflict("personal_dependency_stale")
            source_time = now
            source_text = ""
            if source_message_id:
                source_message = connection.execute(
                    """SELECT m.content,m.created_at FROM assistant_messages m JOIN assistant_threads t ON t.id=m.thread_id
                    WHERE m.workspace_id=%s AND m.id=%s AND m.role='user' AND t.principal_id=%s AND t.space_id=%s""",
                    (
                        self.workspace_id,
                        source_message_id,
                        self.principal_id,
                        space_id,
                    ),
                ).fetchone()
                if source_message is None:
                    raise ValueError("user_source_required")
                source_time = str(source_message["created_at"])
                source_text = str(source_message["content"])
            if source_message_id and not memory_id and clean not in source_text:
                raise ValueError("personal_quote_required")
            if memory_id and source_message_id and clean not in source_text:
                memory = connection.execute(
                    "SELECT text FROM assistant_memories WHERE assistant_memories.workspace_id=%s AND id=%s AND principal_id=%s",
                    (
                        self.workspace_id,
                        memory_id,
                        self.principal_id,
                    ),
                ).fetchone()
                if memory is None or clean not in str(memory["text"]):
                    raise ValueError("personal_quote_required")
            block_id = f"wblock_user_{uuid.uuid4().hex[:20]}"
            historical = bool(re.search(r"当时|那时|曾经|之前|过去", clean))
            validity = None if historical else anchored_validity(clean, source_time)
            uncertain_time = validity is None and has_time_reference(clean)
            blocks = [
                *before["blocks"],
                {
                    "stable_id": block_id,
                    "heading": "我的笔记",
                    "markdown": clean,
                    "source_refs": [],
                    "applicability": "",
                    "assessment": "user_explicit",
                    "relation": "personal_note",
                    "manual_lock": True,
                    "user_input_source": "memory_derived"
                    if memory_id
                    else ("discussion" if source_message_id else "direct_ui"),
                    "created_at": now,
                    "source_message_id": source_message_id,
                    **(
                        {"user_message_id": source_message_id}
                        if source_message_id and not memory_id
                        else {}
                    ),
                    **(
                        {
                            "historical_statement": True,
                            "validity_note": "原话包含未能可靠解释的时间；仅作历史记录，当前安排需核对",
                        }
                        if uncertain_time
                        else ({"historical_statement": True} if historical else {})
                    ),
                    **(validity or {}),
                },
            ]
            version = expected_version + 1
            changed = connection.execute(
                "UPDATE assistant_wiki_pages SET blocks_json=%s, version=%s, updated_at=%s WHERE assistant_wiki_pages.workspace_id=%s AND id=%s AND version=%s",
                (
                    Jsonb(blocks),
                    version,
                    now,
                    self.workspace_id,
                    page_id,
                    expected_version,
                ),
            )
            if changed.rowcount != 1:
                raise AssistantConflict("wiki_version_conflict")
            if memory_id:
                connection.execute(
                    """INSERT INTO assistant_wiki_personal_dependencies(workspace_id,
                        page_id,block_id,memory_id,memory_version,source_message_id,created_at
                    ) VALUES(%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        self.workspace_id,
                        page_id,
                        block_id,
                        memory_id,
                        int(memory_version),
                        source_message_id,
                        now,
                    ),
                )
            after = self._decode_page(
                dict(
                    connection.execute(
                        "SELECT * FROM assistant_wiki_pages WHERE assistant_wiki_pages.workspace_id=%s AND id=%s",
                        (
                            self.workspace_id,
                            page_id,
                        ),
                    ).fetchone()
                )
            )
            self._record_notification_change(
                connection,
                """INSERT INTO assistant_wiki_changes(workspace_id,
                    page_id,version,operation,before_json,after_json,summary,actor,created_at
                ) VALUES(%s,%s,%s,'personal_note_added',%s,%s,'添加个人笔记','user',%s)""",
                (
                    self.workspace_id,
                    page_id,
                    version,
                    Jsonb(before),
                    Jsonb(after),
                    now,
                ),
                cause={"operation_key": operation_key},
            )
            self._save_operation_state(
                connection, page_id, version, before_state, conn=connection
            )
            connection.execute(
                """INSERT INTO assistant_mutation_receipts(workspace_id,
                    operation_key,principal_id,operation,result_json,created_at
                ) VALUES(%s,%s,%s,'wiki_personal_note',%s,%s)""",
                (
                    self.workspace_id,
                    operation_key,
                    self.principal_id,
                    Jsonb(after),
                    now,
                ),
            )
        return self._visible_page(after, conn=conn, snapshot_cache=prepared_sources)

    def save_discussion(
        self,
        *,
        space_id: int,
        title: str,
        purpose: str,
        blocks: list[dict[str, Any]],
        operation_key: str,
        expected_version: int | None = None,
        source_message_id: str | None = None,
        authorized_plan_id: str | None = None,
        authorized_plan_version: int | None = None,
        conn=None,
        prepared_sources=None,
    ) -> dict[str, Any]:
        """Save selected conclusions, with each block's role and current dependencies."""
        if prepared_sources is None:
            prepared_sources = (
                self._prepare_sources_for_write(space_id=space_id)
                if conn is None
                else {}
            )
        title, purpose = title.strip(), purpose.strip()
        if (
            not title
            or len(title) > 120
            or not purpose
            or len(purpose) > 600
            or not 1 <= len(blocks) <= 8
        ):
            raise ValueError("invalid_knowledge_save")
        space = self.store.get_space(space_id, conn=conn)
        if source_message_id is None:
            raise ValueError("user_source_required")
        now = utc_now()
        with self._transaction(conn, operation_key=operation_key) as connection:
            receipt = connection.execute(
                "SELECT result_json FROM assistant_mutation_receipts WHERE assistant_mutation_receipts.workspace_id=%s AND operation_key=%s AND principal_id=%s",
                (
                    self.workspace_id,
                    operation_key,
                    self.principal_id,
                ),
            ).fetchone()
            if receipt:
                return self._visible_page(
                    (receipt["result_json"]),
                    conn=connection,
                    snapshot_cache=prepared_sources,
                )
            message = connection.execute(
                """SELECT m.id,m.content,m.created_at,t.id AS thread_id FROM assistant_messages m
                JOIN assistant_threads t ON t.id=m.thread_id
                WHERE m.workspace_id=%s AND m.id=%s AND m.role='user' AND t.principal_id=%s AND t.space_id=%s""",
                (
                    self.workspace_id,
                    source_message_id,
                    self.principal_id,
                    space_id,
                ),
            ).fetchone()
            if message is None:
                raise ValueError("user_source_required")
            latest = connection.execute(
                "SELECT working_state_json FROM assistant_runs WHERE assistant_runs.workspace_id=%s AND thread_id=%s ORDER BY insertion_seq DESC LIMIT 1",
                (
                    self.workspace_id,
                    message["thread_id"],
                ),
            ).fetchone()
            task_subset = (
                ((latest["working_state_json"]).get("task_subset") or {}).get(
                    "video_ids"
                )
                if latest
                else None
            )
            current_space = connection.execute(
                "SELECT scope_version FROM assistant_spaces WHERE assistant_spaces.workspace_id=%s AND id=%s",
                (
                    self.workspace_id,
                    space_id,
                ),
            ).fetchone()
            if int(current_space["scope_version"]) != int(space["scope_version"]):
                raise AssistantConflict("wiki_scope_changed")
            if authorized_plan_id is not None:
                authorization = connection.execute(
                    """SELECT * FROM assistant_knowledge_plans
                    WHERE assistant_knowledge_plans.workspace_id=%s AND id=%s AND principal_id=%s AND space_id=%s""",
                    (
                        self.workspace_id,
                        authorized_plan_id,
                        self.principal_id,
                        space_id,
                    ),
                ).fetchone()
                if (
                    authorization is None
                    or authorized_plan_version is None
                    or int(authorization["version"]) != authorized_plan_version
                    or int(authorization["scope_version"])
                    != int(current_space["scope_version"])
                    or authorization["status"] != "partial"
                ):
                    raise AssistantConflict("knowledge_plan_authorization_changed")
            issues = self._plan_block_issues(
                connection=connection,
                space=space,
                source_message_id=source_message_id,
                topics=[{"blocks": blocks}],
                conn=connection,
                prepared_sources=prepared_sources,
            )
            if issues:
                raise ValueError("knowledge_topic_invalid:" + ";".join(issues))
            inactive = connection.execute(
                "SELECT status FROM assistant_wiki_pages WHERE assistant_wiki_pages.workspace_id=%s AND principal_id=%s AND space_id=%s AND normalized_title=%s",
                (
                    self.workspace_id,
                    self.principal_id,
                    space_id,
                    self._normalize_title(title),
                ),
            ).fetchone()
            if inactive and inactive["status"] != "active":
                raise AssistantConflict("wiki_page_inactive")
            normalized = self._normalize_title(title)
            row = connection.execute(
                """SELECT * FROM assistant_wiki_pages WHERE assistant_wiki_pages.workspace_id=%s AND principal_id=%s AND space_id=%s
                AND normalized_title=%s AND status='active'""",
                (
                    self.workspace_id,
                    self.principal_id,
                    space_id,
                    normalized,
                ),
            ).fetchone()
            before = self._decode_page(dict(row)) if row else None
            if before and expected_version != int(before["version"]):
                raise AssistantConflict("wiki_version_conflict")
            if not before and expected_version is not None:
                raise AssistantConflict("wiki_page_missing")
            page_id = str(before["id"]) if before else f"awiki_{uuid.uuid4().hex}"
            old_blocks = list(before["blocks"]) if before else []
            before_state = (
                self._operation_state(connection, page_id, conn=connection)
                if before
                else None
            )
            incoming = []
            source_links = []
            personal_links = []
            for item in blocks:
                role = str(item.get("role") or "")
                heading = str(item.get("heading") or "").strip()
                body = str(item.get("markdown") or "").strip()
                refs = list(dict.fromkeys(item.get("source_refs") or []))
                external = item.get("external_sources") or []
                if (
                    role not in {"source", "analysis", "personal"}
                    or not heading
                    or not body
                    or len(body) > 12000
                ):
                    raise ValueError("invalid_knowledge_block")
                if role == "source" and not refs and not external:
                    raise ValueError("source_block_requires_source")
                if role == "personal" and (refs or external):
                    raise ValueError("personal_block_source_conflict")
                if role == "personal":
                    quote = str(item.get("user_quote") or "").strip()
                    quote_message = self._user_quote(
                        connection,
                        space_id=space_id,
                        request_message_id=source_message_id,
                        user_message_id=item.get("user_message_id"),
                        quote=quote,
                        body=body,
                        conn=connection,
                    )
                memory_id, memory_version = (
                    item.get("memory_id"),
                    item.get("memory_version"),
                )
                if bool(memory_id) != (memory_version is not None) or (
                    memory_id and role == "source"
                ):
                    raise ValueError("invalid_memory_dependency")
                block_id = f"wblock_{uuid.uuid4().hex[:20]}"
                revisions = []
                source_view = str(item.get("source_view") or "")
                if source_view and source_view not in {
                    "transcript",
                    "summary",
                    "description",
                    "notes",
                    "metadata",
                    "time",
                }:
                    raise ValueError("invalid_source_view")
                # A mixed block cannot inherit a narrower dependency merely
                # because one of its sources was a transcript. In particular,
                # a corrected publication date must not leave an old date in
                # an otherwise transcript-backed block.
                if (
                    source_view
                    and source_view != "time"
                    and re.search(r"发布时间|收藏时间|\b20\d{2}[-/.年]\d{1,2}", body)
                ):
                    source_view = ""
                for ref in refs:
                    parts = str(ref).split(":")
                    if len(parts) != 3 or parts[0] != "video" or not parts[1].isdigit():
                        raise ValueError("versioned_video_source_required")
                    video_id, revision = int(parts[1]), parts[2]
                    head = connection.execute(
                        "SELECT current_revision FROM assistant_source_heads WHERE assistant_source_heads.workspace_id=%s AND principal_id=%s AND video_id=%s",
                        (
                            self.workspace_id,
                            self.principal_id,
                            video_id,
                        ),
                    ).fetchone()
                    if head is None or str(head["current_revision"]) != revision:
                        raise AssistantConflict("source_revision_changed")
                    if video_id not in self.sources.visible_video_ids(
                        self._scope(space), conn=conn
                    ) or (task_subset and video_id not in task_subset):
                        raise AssistantConflict("wiki_source_out_of_scope")
                    if source_view and not self._read_view_observed(
                        connection,
                        thread_id=str(message["thread_id"]),
                        source_ref=str(ref),
                        view=source_view,
                        conn=connection,
                    ):
                        raise ValueError("source_view_not_observed")
                    revisions.append(revision)
                    source_links.append(
                        (
                            block_id,
                            video_id,
                            revision,
                            f"view:{source_view}" if source_view else "source",
                        )
                    )
                external_links = []
                for source in external:
                    url = str(source.get("url") or "")
                    result_ref = str(source.get("result_ref") or "")
                    if not re.fullmatch(r"https://[^\s]+", url):
                        raise ValueError("invalid_external_url")
                    resolved = self.store.resolve_run_result(
                        result_ref,
                        current_thread_id=str(message["thread_id"]),
                        current_scope_version=int(space["scope_version"]),
                        conn=connection,
                    )
                    if not str(resolved["name"]).startswith(
                        "context7_"
                    ) or url not in json.dumps(resolved["result"], ensure_ascii=False):
                        raise ValueError("external_source_not_in_result")
                    receipt = connection.execute(
                        "SELECT completed_at FROM assistant_tool_calls WHERE assistant_tool_calls.workspace_id=%s AND run_id=%s AND call_id=%s",
                        (
                            self.workspace_id,
                            resolved["run_id"],
                            resolved["call_id"],
                        ),
                    ).fetchone()
                    external_links.append(
                        {
                            "url": url,
                            "result_ref": resolved["result_ref"],
                            "captured_at": str(receipt["completed_at"] or now),
                        }
                    )
                if memory_id:
                    if not self._personal_dependency_current(
                        connection,
                        space_id=space_id,
                        memory_id=str(memory_id),
                        memory_version=int(memory_version),
                        source_message_id=source_message_id,
                        conn=connection,
                    ):
                        raise AssistantConflict("personal_dependency_stale")
                    personal_links.append(
                        (block_id, str(memory_id), int(memory_version))
                    )
                value = {
                    "stable_id": block_id,
                    "heading": heading[:160],
                    "markdown": body,
                    "source_refs": revisions,
                    "applicability": str(item.get("applicability") or "")[:600],
                    "assessment": {
                        "source": "source_reported",
                        "analysis": "system_synthesis",
                        "personal": "user_explicit",
                    }[role],
                    "relation": {
                        "source": "discussion_source",
                        "analysis": "discussion_analysis",
                        "personal": "personal_note",
                    }[role],
                    "manual_lock": role == "personal",
                    "user_input_source": "memory_derived"
                    if memory_id
                    else "discussion",
                    "source_message_id": source_message_id,
                    "created_at": now,
                    **({"source_view": source_view} if source_view else {}),
                    **({"external_sources": external_links} if external_links else {}),
                    **(
                        {"user_quote": quote, "user_message_id": quote_message["id"]}
                        if role == "personal"
                        else {}
                    ),
                    **(
                        {"evidence_ref": item["evidence_ref"]}
                        if item.get("evidence_ref")
                        else {}
                    ),
                }
                if role == "personal" and not memory_id:
                    historical = bool(re.search(r"当时|那时|曾经|之前|过去", body))
                    validity = (
                        None
                        if historical
                        else anchored_validity(body, str(quote_message["created_at"]))
                    )
                    if validity is None and has_time_reference(body):
                        value["historical_statement"] = True
                        value["validity_note"] = (
                            "原话包含未能可靠解释的时间；仅作历史记录，当前安排需核对"
                        )
                    elif historical:
                        value["historical_statement"] = True
                    elif validity:
                        value.update(validity)
                incoming.append(value)
            version = int(before["version"]) + 1 if before else 1
            for tomb in old_blocks:
                if tomb.get("deleted") and any(
                    (
                        " ".join(tomb.get("heading", "").split()),
                        " ".join(tomb.get("markdown", "").split()),
                    )
                    == (
                        " ".join(block["heading"].split()),
                        " ".join(block["markdown"].split()),
                    )
                    for block in incoming
                ):
                    tomb.update(deletion_released=True, lifecycle_version=version)
            all_blocks = old_blocks + incoming
            if before and authorized_plan_id is not None:
                # A new discussion plan edits matching headings on the same page.
                # Unmentioned blocks and human content keep their original identity.
                headings = [" ".join(block["heading"].split()) for block in incoming]
                if len(headings) != len(set(headings)):
                    raise AssistantConflict("wiki_block_target_ambiguous")
                for block in incoming:
                    matches = [
                        old
                        for old in old_blocks
                        if not old.get("deleted")
                        and " ".join(old["heading"].split())
                        == " ".join(block["heading"].split())
                    ]
                    if len(matches) > 1:
                        raise AssistantConflict("wiki_block_target_ambiguous")
                    if not matches:
                        continue
                    old = matches[0]
                    if old.get("manual_lock"):
                        if all(
                            old.get(k) == block.get(k)
                            for k in (
                                "markdown",
                                "assessment",
                                "user_quote",
                                "user_message_id",
                                "applicability",
                            )
                        ):
                            all_blocks.remove(block)
                        # Distinct new content may be appended, as before; it must
                        # never overwrite an independently edited or personal block.
                    else:
                        all_blocks.remove(
                            block
                        )  # remove the appended copy, keeping page order
                        all_blocks[all_blocks.index(old)] = block
                        for table in (
                            "assistant_wiki_dependencies",
                            "assistant_wiki_personal_dependencies",
                        ):
                            connection.execute(
                                f"DELETE FROM {table} WHERE workspace_id=%s AND page_id=%s AND block_id=%s",
                                (self.workspace_id, page_id, old["stable_id"]),
                            )
                active_ids = {block["stable_id"] for block in all_blocks}
                source_links = [link for link in source_links if link[0] in active_ids]
                personal_links = [
                    link for link in personal_links if link[0] in active_ids
                ]
            if before:
                changed = connection.execute(
                    """UPDATE assistant_wiki_pages SET blocks_json=%s,version=%s,updated_at=%s
                    WHERE assistant_wiki_pages.workspace_id=%s AND id=%s AND version=%s""",
                    (
                        Jsonb(all_blocks),
                        version,
                        now,
                        self.workspace_id,
                        page_id,
                        before["version"],
                    ),
                )
                if changed.rowcount != 1:
                    raise AssistantConflict("wiki_version_conflict")
            else:
                connection.execute(
                    """INSERT INTO assistant_wiki_pages(workspace_id,id,principal_id,space_id,normalized_title,title,
                    aliases_json,page_type,summary,blocks_json,version,status,scope_version,created_at,updated_at)
                    VALUES(%s,%s,%s,%s,%s,%s,'[]','topic',%s,%s,1,'active',%s,%s,%s)""",
                    (
                        self.workspace_id,
                        page_id,
                        self.principal_id,
                        space_id,
                        normalized,
                        title,
                        purpose,
                        Jsonb(all_blocks),
                        space["scope_version"],
                        now,
                        now,
                    ),
                )
            for block_id, video_id, revision, dependency_kind in source_links:
                connection.execute(
                    """INSERT INTO assistant_wiki_dependencies(workspace_id,page_id,block_id,source_revision,video_id,
                    dependency_kind,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        self.workspace_id,
                        page_id,
                        block_id,
                        revision,
                        video_id,
                        dependency_kind,
                        now,
                    ),
                )
                connection.execute(
                    """INSERT INTO assistant_wiki_materials(workspace_id,page_id,video_id,source_revision,relation,
                    status,created_at,updated_at) VALUES(%s,%s,%s,%s,'supports_block','integrated',%s,%s)
                    ON CONFLICT(page_id,video_id) DO UPDATE SET source_revision=excluded.source_revision,
                    relation='supports_block',updated_at=excluded.updated_at""",
                    (
                        self.workspace_id,
                        page_id,
                        video_id,
                        revision,
                        now,
                        now,
                    ),
                )
            for block_id, memory_id, memory_version in personal_links:
                connection.execute(
                    """INSERT INTO assistant_wiki_personal_dependencies
                    (workspace_id,page_id,block_id,memory_id,memory_version,source_message_id,created_at)
                    VALUES(%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        self.workspace_id,
                        page_id,
                        block_id,
                        memory_id,
                        memory_version,
                        source_message_id,
                        now,
                    ),
                )
            after = self._decode_page(
                dict(
                    connection.execute(
                        "SELECT * FROM assistant_wiki_pages WHERE assistant_wiki_pages.workspace_id=%s AND id=%s",
                        (
                            self.workspace_id,
                            page_id,
                        ),
                    ).fetchone()
                )
            )
            self._record_notification_change(
                connection,
                """INSERT INTO assistant_wiki_changes(workspace_id,page_id,version,operation,before_json,after_json,
                summary,actor,created_at) VALUES(%s,%s,%s,'discussion_saved',%s,%s,%s,'user',%s)""",
                (
                    self.workspace_id,
                    page_id,
                    version,
                    Jsonb(before) if before else None,
                    Jsonb(after),
                    "保存讨论成果",
                    now,
                ),
                cause={
                    "operation_key": operation_key,
                    "source_message_ids": [source_message_id],
                    "thread_id": message["thread_id"],
                },
                plan=dict(authorization) if authorized_plan_id else None,
            )
            self._save_operation_state(
                connection, page_id, version, before_state, conn=connection
            )
            connection.execute(
                """INSERT INTO assistant_mutation_receipts
                (workspace_id,operation_key,principal_id,operation,result_json,created_at)
                VALUES(%s,%s,%s,'knowledge_save',%s,%s)""",
                (
                    self.workspace_id,
                    operation_key,
                    self.principal_id,
                    Jsonb(after),
                    now,
                ),
            )
        return self._visible_page(after, conn=conn, snapshot_cache=prepared_sources)

    def save_feedback(self, plan: dict, *, conn=None) -> dict:
        """Receipt-backed UI hints. Actual undo still runs existing CAS operations."""
        items = []
        with self.db.connect(conn) as connection:
            for index, outcome in plan.get("results", {}).items():
                if outcome.get("status") != "completed":
                    continue
                page_id, version = outcome["page_id"], int(outcome["version"])
                page = connection.execute(
                    "SELECT title,version,status FROM assistant_wiki_pages WHERE assistant_wiki_pages.workspace_id=%s AND id=%s AND principal_id=%s AND space_id=%s",
                    (
                        self.workspace_id,
                        page_id,
                        self.principal_id,
                        plan["space_id"],
                    ),
                ).fetchone()
                change = connection.execute(
                    "SELECT before_json FROM assistant_wiki_changes WHERE assistant_wiki_changes.workspace_id=%s AND page_id=%s AND version=%s AND operation='discussion_saved'",
                    (
                        self.workspace_id,
                        page_id,
                        version,
                    ),
                ).fetchone()
                undo = None
                if (
                    page
                    and page["status"] == "active"
                    and int(page["version"]) == version
                    and change
                ):
                    if change["before_json"] is None:
                        undo = {"kind": "archive"}
                    else:
                        before = change["before_json"]
                        undo = {
                            "kind": "revert",
                            "target_version": int(before["version"]),
                        }
                items.append(
                    {
                        "page_id": page_id,
                        "version": version,
                        "operation_key": f"wiki:{page_id}:{version}",
                        "title": page["title"] if page else "知识页",
                        "undo": undo,
                    }
                )
        return {
            "kind": "wiki",
            "operation_key": f"plan:{plan['id']}:{plan['version']}",
            "space_id": plan["space_id"],
            "count": len(items),
            "items": items,
        }

    def _read_view_observed(
        self, connection: Any, *, thread_id: str, source_ref: str, view: str, conn=None
    ) -> bool:
        # Attached descriptions/metadata can be genuinely delivered even when
        # the read's requested view was a transcript. Use confirmed input facts.
        conn = connection if conn is None else conn
        delivered = self.store.confirmed_context_materials(
            connection, thread_id=thread_id
        )
        for run in connection.execute(
            "SELECT working_state_json FROM assistant_runs WHERE assistant_runs.workspace_id=%s AND thread_id=%s",
            (
                self.workspace_id,
                thread_id,
            ),
        ):
            delivered.extend(
                (run["working_state_json"] or {}).get("model_delivered_materials") or []
            )
        for material in delivered:
            if (
                (
                    material.get("kind") == "collection_read"
                    or view in {"metadata", "time"}
                )
                and material.get("source_ref") == source_ref
                and material.get("view") == view
                and material.get("projection") != "结果索引"
            ):
                return True
        return False

    def _source_dependency_current(
        self,
        *,
        video_id: int,
        old_revision: str,
        current_revision: str,
        dependency_kind: str,
        cache: dict[str, dict[str, Any]],
        conn=None,
    ) -> bool:
        if old_revision == current_revision:
            return True
        if not dependency_kind.startswith("view:") or not current_revision:
            return False
        try:
            if old_revision not in cache:
                if conn is not None:
                    raise AssistantConflict("wiki_snapshot_prepare_stale")
                cache[old_revision] = self.sources._capture_or_load(
                    video_id, old_revision
                ).snapshot
            if current_revision not in cache:
                if conn is not None:
                    raise AssistantConflict("wiki_snapshot_prepare_stale")
                cache[current_revision] = self.sources._capture_or_load(
                    video_id, current_revision
                ).snapshot
            old, new = cache[old_revision], cache[current_revision]
        except (KeyError, OSError, ValueError):
            return False
        view = dependency_kind.removeprefix("view:")
        if view == "transcript":
            return all(
                old.get("material_hashes", {}).get(key)
                == new.get("material_hashes", {}).get(key)
                for key in ("raw_subtitle", "transcript")
            )
        if view == "summary":
            return old.get("material_hashes", {}).get("summary") == new.get(
                "material_hashes", {}
            ).get("summary")
        if view == "description":
            return old.get("metadata", {}).get("description") == new.get(
                "metadata", {}
            ).get("description")
        if view == "notes":
            return [item.get("content") for item in old.get("notes", [])] == [
                item.get("content") for item in new.get("notes", [])
            ]
        if view == "metadata":
            excluded = {
                "published_at",
                "metadata_observed_at",
                "discovered_at",
                "active_revision",
            }
            return {
                key: value
                for key, value in old.get("metadata", {}).items()
                if key not in excluded
            } == {
                key: value
                for key, value in new.get("metadata", {}).items()
                if key not in excluded
            }
        if view == "time":
            return old.get("metadata", {}).get("published_at") == new.get(
                "metadata", {}
            ).get("published_at") and old.get("membership_hash") == new.get(
                "membership_hash"
            )
        return False

    def _user_quote(
        self,
        connection: Any,
        *,
        space_id: int,
        request_message_id: str,
        user_message_id: str | None,
        quote: str,
        body: str,
        conn=None,
    ) -> dict:
        conn = connection if conn is None else conn
        repair = connection.execute(
            "SELECT payload_json FROM assistant_knowledge_plans WHERE assistant_knowledge_plans.workspace_id=%s AND source_message_id=%s AND principal_id=%s AND space_id=%s ORDER BY updated_at DESC LIMIT 1",
            (
                self.workspace_id,
                request_message_id,
                self.principal_id,
                space_id,
            ),
        ).fetchone()
        limit_message_id = (
            (repair["payload_json"])
            .get("save_request", {})
            .get("last_repair_message_id")
            if repair
            else None
        ) or request_message_id
        row = connection.execute(
            """SELECT m.* FROM assistant_messages m JOIN assistant_threads t ON t.id=m.thread_id
            WHERE m.workspace_id=%s AND m.id=%s AND m.role='user' AND t.principal_id=%s AND t.space_id=%s
            AND m.thread_id=(SELECT thread_id FROM assistant_messages WHERE id=%s)
            AND m.seq<=(SELECT seq FROM assistant_messages WHERE id=%s)""",
            (
                self.workspace_id,
                user_message_id or request_message_id,
                self.principal_id,
                space_id,
                request_message_id,
                limit_message_id,
            ),
        ).fetchone()
        suppressed = self._memories().suppressed_source_message_ids(
            space_id=space_id, conn=conn
        )
        if (
            row is None
            or str(row["id"]) in suppressed
            or not quote.strip()
            or quote.strip() not in str(row["content"])
        ):
            raise ValueError("personal_quote_required")
        return dict(row)

    def _validate_save_answer(
        self, connection: Any, message_id: str, space: dict, *, conn=None
    ) -> None:
        conn = connection if conn is None else conn
        row = connection.execute(
            "SELECT r.working_state_json,m.thread_id FROM assistant_runs r JOIN assistant_messages m ON m.run_id=r.id WHERE r.workspace_id=%s AND m.id=%s",
            (
                self.workspace_id,
                message_id,
            ),
        ).fetchone()
        if not row:
            raise AssistantConflict("user_source_required")
        plan = connection.execute(
            "SELECT payload_json FROM assistant_knowledge_plans WHERE assistant_knowledge_plans.workspace_id=%s AND source_message_id=%s AND principal_id=%s AND space_id=%s ORDER BY updated_at DESC LIMIT 1",
            (
                self.workspace_id,
                message_id,
                self.principal_id,
                int(space["id"]),
            ),
        ).fetchone()
        binding = (
            (plan["payload_json"]).get("save_request", {})
            if plan
            else (row["working_state_json"] or {}).get("knowledge_save", {})
        )
        answer_ids = binding.get("answer_message_ids") or (
            [binding["answer_message_id"]] if binding.get("answer_message_id") else []
        )
        if not answer_ids:
            return
        from shiliu.assistant.tools import AssistantToolRegistry

        registry = AssistantToolRegistry(
            sources=self.sources,
            memories=self._memories(),
            store=self.store,
            wiki=self,
        )
        for answer_id in answer_ids:
            answer = self.store.knowledge_message(
                answer_id, thread_id=row["thread_id"], conn=conn
            )
            refs = (answer.get("provider_payload_json") or {}).get(
                "dependency_refs"
            ) or []
            if refs and not registry.dependency_refs_valid(
                refs, int(space["id"]), row["thread_id"], int(space["scope_version"])
            ):
                raise AssistantConflict("save_answer_dependencies_changed")

    def _source_delivered(
        self,
        connection: Any,
        *,
        message_id: str,
        ref: str,
        view: str,
        evidence_ref: str = "",
        conn=None,
    ) -> bool:
        conn = connection if conn is None else conn
        message = connection.execute(
            "SELECT thread_id FROM assistant_messages WHERE assistant_messages.workspace_id=%s AND id=%s",
            (
                self.workspace_id,
                message_id,
            ),
        ).fetchone()
        if not message:
            return False
        suppressed = self._memories().suppressed_source_message_ids(
            space_id=int(
                connection.execute(
                    "SELECT space_id FROM assistant_threads WHERE assistant_threads.workspace_id=%s AND id=%s",
                    (
                        self.workspace_id,
                        message["thread_id"],
                    ),
                ).fetchone()["space_id"]
            ),
            conn=conn,
        )
        states = []
        for run in connection.execute(
            "SELECT id,working_state_json FROM assistant_runs WHERE assistant_runs.workspace_id=%s AND thread_id=%s",
            (
                self.workspace_id,
                message["thread_id"],
            ),
        ):
            user_ids = {
                r["id"]
                for r in connection.execute(
                    "SELECT id FROM assistant_messages WHERE assistant_messages.workspace_id=%s AND run_id=%s AND role='user'",
                    (
                        self.workspace_id,
                        run["id"],
                    ),
                )
            }
            if not user_ids.intersection(suppressed):
                state = run["working_state_json"] or {}
                state["model_delivered_materials"] = [
                    *(state.get("model_delivered_materials") or []),
                    *self.store.confirmed_context_materials(
                        connection, thread_id=message["thread_id"], run_id=run["id"]
                    ),
                ]
                states.append(state)
        for state in states:
            for material in state.get("model_delivered_materials") or []:
                if (
                    view in {"metadata", "time"}
                    and material.get("source_ref") == ref
                    and material.get("view") == view
                    and material.get("projection") != "结果索引"
                ):
                    return True
                if material.get("projection") in {
                    "结果索引",
                    "搜索候选",
                } or material.get("kind") in {
                    "search_knowledge",
                    "collection_search",
                    "knowledge_search",
                }:
                    continue
                if material.get("view") in {
                    "result_index",
                    "overview",
                    "知识页目录／命中摘要",
                }:
                    continue
                if (
                    not view
                    and ref.startswith("run-result:")
                    and material.get("source_ref") == ref
                    and str(material.get("kind") or "").startswith("context7_")
                    and material.get("view") == "公开文档"
                ):
                    return True
                if material.get("source_ref") == ref and (
                    material.get("view") == view
                    if view
                    else material.get("view")
                    in {"transcript", "summary", "description", "notes"}
                ):
                    return True
                if (
                    evidence_ref
                    and material.get("source_ref") == evidence_ref
                    and ref in (material.get("lineage_refs") or [])
                    and not view
                ):
                    parts = evidence_ref.split(":")
                    if len(parts) == 3 and parts[0] == "wiki":
                        page = connection.execute(
                            "SELECT version,status FROM assistant_wiki_pages WHERE assistant_wiki_pages.workspace_id=%s AND id=%s AND principal_id=%s",
                            (
                                self.workspace_id,
                                parts[1],
                                self.principal_id,
                            ),
                        ).fetchone()
                        if (
                            page
                            and page["status"] == "active"
                            and str(page["version"]) == parts[2]
                        ):
                            visible = self.get_page(
                                parts[1],
                                space_id=int(
                                    connection.execute(
                                        "SELECT space_id FROM assistant_threads WHERE assistant_threads.workspace_id=%s AND id=(SELECT thread_id FROM assistant_messages WHERE id=%s)",
                                        (
                                            self.workspace_id,
                                            message_id,
                                        ),
                                    ).fetchone()["space_id"]
                                ),
                                conn=conn,
                            )
                            delivered_ids = set(
                                material.get("position", {}).get("block_ids") or []
                            )
                            if delivered_ids and delivered_ids.issubset(
                                {block["stable_id"] for block in visible["blocks"]}
                            ):
                                return True
        return False

    @staticmethod
    def _save_issues(issues: list[str], *, topic_offset: int = 0) -> list[dict]:
        fields = {
            "personal_quote_required": "user_message_id",
            "personal_block_source_conflict": "source_refs",
            "source_block_requires_source": "source_refs",
            "versioned_video_source_required": "source_refs",
            "source_revision_changed": "source_refs",
            "wiki_source_out_of_scope": "source_refs",
            "source_view_not_observed": "source_view",
            "source_not_delivered": "source_refs",
            "invalid_memory_dependency": "memory_id",
            "personal_dependency_stale": "memory_id",
            "external_source_not_delivered": "external_sources",
            "external_source_not_in_result": "external_sources",
        }
        result = []
        for issue in dict.fromkeys(issues):
            match = re.match(r"topic\[(\d+)\]\.block\[(\d+)\].*?:([^:]+)$", issue)
            if match:
                code = match[3]
                path = f"topics[{int(match[1]) - 1 + topic_offset}].blocks[{int(match[2]) - 1}].{fields.get(code, 'markdown')}"
            else:
                code = issue.split(":")[-1]
                topic_match = re.match(r"topic\[(\d+)\]:", issue)
                ti = (
                    int(topic_match[1]) - 1 + topic_offset
                    if topic_match
                    else topic_offset
                )
                path = (
                    f"topics[{ti}].expected_version"
                    if "version" in code or code == "wiki_page_missing"
                    else f"topics[{ti}]"
                )
            detail = {}
            if '|{"source_ref":' in issue:
                try:
                    detail = json.loads(
                        '{"source_ref":'
                        + issue.split('|{"source_ref":', 1)[1].rsplit(":", 1)[0]
                    )
                except ValueError:
                    pass
            message = (
                (
                    f"{path}：{detail['source_ref']} 请求视图 {detail['requested_view'] or '未声明'}；"
                    f"已交付视图 {', '.join(detail['observed_views']) or '未找到可验证交付'}（{code}）"
                )
                if detail
                else issue
            )
            result.append(
                {
                    "path": path,
                    "code": code,
                    "message": message,
                    **detail,
                    "action": (
                        "personal 需要绑定真实用户消息及其中的原话；正文可忠实归纳，不能伪造引语或把助手分析当用户表达。"
                        if code == "personal_quote_required"
                        else "沿原计划重交该未成功主题，成功项不动。source_refs 使用读取回执中的完整 video:ID:revision，不能只填裸版本哈希；依据已读 Wiki 正文时填写该页 evidence_ref（wiki:page_id:version），不冒充重读原材料。缺依据才定点读取；不要删除来源或改成 analysis 绕过校验，不需重复确认同一保存授权"
                        if code
                        in {"versioned_video_source_required", "source_not_delivered"}
                        else "沿原计划重交该未成功主题；成功项不动。按真实交付视图纠正，缺依据才定点读取；不需重复确认同一保存授权"
                    ),
                }
            )
        return result

    def _plan_block_issues(
        self,
        *,
        connection: Any,
        space: dict[str, Any],
        source_message_id: str,
        topics: list[dict[str, Any]],
        conn=None,
        prepared_sources=None,
    ) -> list[str]:
        """Check the save prerequisites before a plan is offered for confirmation."""
        if prepared_sources is None:
            prepared_sources = {} if conn is None else {}
        conn = connection if conn is None else conn
        message = connection.execute(
            """SELECT m.content,t.id AS thread_id FROM assistant_messages m
            JOIN assistant_threads t ON t.id=m.thread_id
            WHERE m.workspace_id=%s AND m.id=%s AND m.role='user' AND t.principal_id=%s AND t.space_id=%s""",
            (
                self.workspace_id,
                source_message_id,
                self.principal_id,
                int(space["id"]),
            ),
        ).fetchone()
        if message is None:
            return ["user_source_required"]
        if source_message_id in self._memories().suppressed_source_message_ids(
            space_id=int(space["id"]), conn=conn
        ):
            return ["user_source_suppressed"]
        self._validate_save_answer(connection, source_message_id, space, conn=conn)
        issues: list[str] = []
        scope = self._scope(self.store.task_space(str(message["thread_id"]), conn=conn))
        for topic_index, topic in enumerate(topics, 1):
            if topic.get("title") and "expected_version" in topic:
                page = connection.execute(
                    "SELECT version FROM assistant_wiki_pages WHERE assistant_wiki_pages.workspace_id=%s AND principal_id=%s AND space_id=%s AND normalized_title=%s AND status='active'",
                    (
                        self.workspace_id,
                        self.principal_id,
                        int(space["id"]),
                        self._normalize_title(topic["title"]),
                    ),
                ).fetchone()
                if page and topic.get("expected_version") != int(page["version"]):
                    issues.append(f"topic[{topic_index}]:wiki_version_conflict")
                elif not page and topic.get("expected_version") is not None:
                    issues.append(f"topic[{topic_index}]:wiki_page_missing")
            for block_index, block in enumerate(topic.get("blocks") or [], 1):
                position = f"topic[{topic_index}].block[{block_index}]({str(block.get('heading') or '')[:40]})"
                role = str(block.get("role") or "")
                body = str(block.get("markdown") or "").strip()
                refs = list(dict.fromkeys(block.get("source_refs") or []))
                external = block.get("external_sources") or []
                if (
                    role not in {"source", "analysis", "personal"}
                    or not str(block.get("heading") or "").strip()
                    or not body
                    or len(body) > 12000
                ):
                    issues.append(f"{position}:invalid_knowledge_block")
                    continue
                if role == "source" and not refs and not external:
                    issues.append(f"{position}:source_block_requires_source")
                if role == "personal":
                    if refs or external:
                        issues.append(f"{position}:personal_block_source_conflict")
                    quote = str(block.get("user_quote") or "").strip()
                    try:
                        self._user_quote(
                            connection,
                            space_id=int(space["id"]),
                            request_message_id=source_message_id,
                            user_message_id=block.get("user_message_id"),
                            quote=quote,
                            body=body,
                            conn=conn,
                        )
                    except ValueError:
                        issues.append(f"{position}:personal_quote_required")
                memory_id, memory_version = (
                    block.get("memory_id"),
                    block.get("memory_version"),
                )
                if bool(memory_id) != (memory_version is not None) or (
                    memory_id and role == "source"
                ):
                    issues.append(f"{position}:invalid_memory_dependency")
                elif memory_id and not self._personal_dependency_current(
                    connection,
                    space_id=int(space["id"]),
                    memory_id=str(memory_id),
                    memory_version=int(memory_version),
                    source_message_id=source_message_id,
                    conn=conn,
                ):
                    issues.append(f"{position}:personal_dependency_stale")
                for ref in refs:
                    parts = str(ref).split(":")
                    if len(parts) != 3 or parts[0] != "video" or not parts[1].isdigit():
                        issues.append(f"{position}:versioned_video_source_required")
                        continue
                    head = connection.execute(
                        "SELECT current_revision FROM assistant_source_heads WHERE assistant_source_heads.workspace_id=%s AND principal_id=%s AND video_id=%s",
                        (
                            self.workspace_id,
                            self.principal_id,
                            int(parts[1]),
                        ),
                    ).fetchone()
                    if head is None or str(head["current_revision"]) != parts[2]:
                        issues.append(f"{position}:source_revision_changed")
                    elif not self.sources.source_refs_visible(
                        [str(ref)], scope, conn=conn
                    ):
                        issues.append(f"{position}:wiki_source_out_of_scope")
                    source_view = str(block.get("source_view") or "")
                    delivered = self._source_delivered(
                        connection,
                        message_id=source_message_id,
                        ref=str(ref),
                        view=source_view,
                        evidence_ref=str(block.get("evidence_ref") or ""),
                        conn=conn,
                    )
                    view_observed = not source_view or self._read_view_observed(
                        connection,
                        thread_id=str(message["thread_id"]),
                        source_ref=str(ref),
                        view=source_view,
                        conn=conn,
                    )
                    if not delivered or not view_observed:
                        # Diagnostics are assembled only on failure, never on the normal save path.
                        suppressed = self._memories().suppressed_source_message_ids(
                            space_id=int(space["id"]), conn=conn
                        )
                        invalid_runs = {
                            r["run_id"]
                            for r in connection.execute(
                                "SELECT run_id,id FROM assistant_messages WHERE assistant_messages.workspace_id=%s AND thread_id=%s AND role='user'",
                                (
                                    self.workspace_id,
                                    str(message["thread_id"]),
                                ),
                            )
                            if r["id"] in suppressed
                        }
                        observed_views = sorted(
                            {
                                str(material.get("view"))
                                for row in connection.execute(
                                    "SELECT id,working_state_json FROM assistant_runs WHERE assistant_runs.workspace_id=%s AND thread_id=%s",
                                    (
                                        self.workspace_id,
                                        str(message["thread_id"]),
                                    ),
                                )
                                if row["id"] not in invalid_runs
                                for material in (row["working_state_json"] or {}).get(
                                    "model_delivered_materials", []
                                )
                                if material.get("source_ref") == str(ref)
                                and material.get("kind") == "collection_read"
                                and material.get("projection")
                                not in {"结果索引", "搜索候选"}
                            }
                        )
                        source_position = (
                            position
                            + "|"
                            + json.dumps(
                                {
                                    "source_ref": str(ref),
                                    "requested_view": source_view,
                                    "observed_views": observed_views,
                                },
                                ensure_ascii=False,
                            )
                        )
                        if not delivered:
                            issues.append(f"{source_position}:source_not_delivered")
                        if not view_observed:
                            issues.append(f"{source_position}:source_view_not_observed")
                for source in external:
                    url = (
                        str(source.get("url") or "") if isinstance(source, dict) else ""
                    )
                    result_ref = (
                        str(source.get("result_ref") or "")
                        if isinstance(source, dict)
                        else ""
                    )
                    if not re.fullmatch(r"https://[^\s]+", url):
                        issues.append(f"{position}:invalid_external_url")
                        continue
                    try:
                        resolved = self.store.resolve_run_result(
                            result_ref,
                            current_thread_id=str(message["thread_id"]),
                            current_scope_version=int(space["scope_version"]),
                            conn=conn,
                        )
                    except (ValueError, KeyError, AssistantConflict):
                        issues.append(f"{position}:external_source_not_in_result")
                        continue
                    if not str(resolved["name"]).startswith(
                        "context7_"
                    ) or url not in json.dumps(resolved["result"], ensure_ascii=False):
                        issues.append(f"{position}:external_source_not_in_result")
                    elif not self._source_delivered(
                        connection,
                        message_id=source_message_id,
                        ref=str(resolved["result_ref"]),
                        view="",
                        conn=conn,
                    ):
                        issues.append(f"{position}:external_source_not_delivered")
        return issues

    def propose_discussion(
        self,
        *,
        space_id: int,
        topics: list[dict[str, Any]],
        omitted: list[str],
        source_message_id: str,
        request_key: str,
        allow_direct_partial: bool = False,
        save_request: dict | None = None,
        conn=None,
        prepared_sources=None,
    ) -> dict[str, Any]:
        if prepared_sources is None:
            prepared_sources = (
                self._prepare_sources_for_write(space_id=space_id)
                if conn is None
                else {}
            )
        if not 1 <= len(topics) <= 6 or not all(
            isinstance(item, dict) for item in topics
        ):
            raise ValueError("invalid_knowledge_plan")
        space = self.store.get_space(space_id, conn=conn)
        with self._transaction(conn) as connection:
            message = connection.execute(
                """SELECT m.content FROM assistant_messages m JOIN assistant_threads t ON t.id=m.thread_id
                WHERE m.workspace_id=%s AND m.id=%s AND m.role='user' AND t.principal_id=%s AND t.space_id=%s""",
                (
                    self.workspace_id,
                    source_message_id,
                    self.principal_id,
                    space_id,
                ),
            ).fetchone()
            if message is None:
                raise ValueError("user_source_required")
            if allow_direct_partial:
                if not str(message["content"]).strip():
                    raise AssistantConflict("user_source_required")
            plan_id = (
                "akplan_"
                + hashlib.sha256(
                    f"{self.principal_id}:{space_id}:{source_message_id}:{request_key}".encode()
                ).hexdigest()[:28]
            )
            existing = connection.execute(
                "SELECT * FROM assistant_knowledge_plans WHERE assistant_knowledge_plans.workspace_id=%s AND id=%s",
                (
                    self.workspace_id,
                    plan_id,
                ),
            ).fetchone()
            if existing:
                previous = self._decode_knowledge_plan(dict(existing))
                frozen = previous["payload"].get("save_request") or {}
                if save_request and any(
                    frozen.get(k, []) != save_request.get(k, [])
                    for k in ("answer_message_ids", "user_message_ids")
                    if k in frozen
                ):
                    raise AssistantConflict("save_target_changed_use_new_request")
                return self._present_knowledge_plan(
                    previous, conn=connection, prepared_sources=prepared_sources
                )
            prepared = []
            names = set()
            for topic_index, item in enumerate(topics):
                title = str(item.get("title") or "").strip()
                purpose = str(item.get("purpose") or "").strip()
                blocks = item.get("blocks") or []
                normalized = self._normalize_title(title)
                if (
                    not normalized
                    or normalized in names
                    or not purpose
                    or not 1 <= len(blocks) <= 8
                ):
                    raise ValueError(
                        f"topics[{topic_index}].title:invalid_knowledge_plan_topic"
                    )
                names.add(normalized)
                page = connection.execute(
                    """SELECT id,version FROM assistant_wiki_pages WHERE assistant_wiki_pages.workspace_id=%s AND principal_id=%s AND space_id=%s
                    AND normalized_title=%s AND status='active'""",
                    (
                        self.workspace_id,
                        self.principal_id,
                        space_id,
                        normalized,
                    ),
                ).fetchone()
                refs = sorted(
                    {
                        str(ref)
                        for block in blocks
                        for ref in block.get("source_refs", [])
                    }
                )
                if (
                    refs
                    and not allow_direct_partial
                    and not self.sources.source_refs_visible(
                        refs, self._scope(space), conn=conn
                    )
                ):
                    raise ValueError("source_out_of_scope")
                prepared.append(
                    {
                        "title": title,
                        "purpose": purpose,
                        "blocks": blocks,
                        "source_refs": refs,
                        "cross_references": item.get("cross_references") or [],
                        "omitted": item.get("omitted") or [],
                        "page_id": str(page["id"]) if page else None,
                        "expected_version": (
                            item.get("expected_version")
                            if item.get("expected_version") is not None
                            else int(page["version"])
                            if page
                            else item.get("expected_version")
                        ),
                    }
                )
            issues = self._plan_block_issues(
                connection=connection,
                space=space,
                source_message_id=source_message_id,
                topics=prepared,
                conn=connection,
                prepared_sources=prepared_sources,
            )
            if issues and not allow_direct_partial and save_request is None:
                raise ValueError(
                    "knowledge_plan_not_confirmable:" + ";".join(issues[:12])
                )
            now = utc_now()
            self._notify_plan(
                connection,
                dict(
                    connection.execute(
                        "INSERT INTO assistant_knowledge_plans(workspace_id,id,principal_id,space_id,version,scope_version,\n                source_message_id,payload_json,results_json,status,created_at,updated_at)\n                VALUES(%s,%s,%s,%s,1,%s,%s,%s,'{}','pending',%s,%s) RETURNING *",
                        (
                            self.workspace_id,
                            plan_id,
                            self.principal_id,
                            space_id,
                            space["scope_version"],
                            source_message_id,
                            Jsonb(
                                {
                                    "topics": prepared,
                                    "omitted": omitted[:20],
                                    "direct_authorized": bool(allow_direct_partial),
                                    **(
                                        {
                                            "save_request": save_request,
                                            "stable_topic_receipts": True,
                                        }
                                        if save_request
                                        else {}
                                    ),
                                }
                            ),
                            now,
                            now,
                        ),
                    ).fetchone()
                ),
            )
            row = connection.execute(
                "SELECT * FROM assistant_knowledge_plans WHERE assistant_knowledge_plans.workspace_id=%s AND id=%s",
                (
                    self.workspace_id,
                    plan_id,
                ),
            ).fetchone()
        return self._present_knowledge_plan(
            self._decode_knowledge_plan(dict(row)),
            conn=conn,
            prepared_sources=prepared_sources,
        )

    def save_discussion_topics(
        self,
        *,
        space_id: int,
        topics: list[dict[str, Any]],
        omitted: list[str],
        source_message_id: str,
        request_key: str,
        save_request: dict | None = None,
        conn=None,
    ) -> dict[str, Any]:
        # The authorization is the current user's actual message, not a model
        # supplied flag or an old pending plan. Keep the existing plan validator,
        # per-page receipts, version checks and partial-result handling.
        with self.db.connect(conn) as connection:
            row = connection.execute(
                """SELECT m.content FROM assistant_messages m
                JOIN assistant_threads t ON t.id=m.thread_id
                WHERE m.workspace_id=%s AND m.id=%s AND m.role='user' AND t.principal_id=%s AND t.space_id=%s""",
                (
                    self.workspace_id,
                    source_message_id,
                    self.principal_id,
                    space_id,
                ),
            ).fetchone()
        if row is None:
            raise AssistantConflict("explicit_knowledge_save_required")
        plan = self.propose_discussion(
            space_id=space_id,
            topics=topics,
            omitted=omitted,
            source_message_id=source_message_id,
            request_key=request_key,
            allow_direct_partial=True,
            save_request=save_request,
            conn=conn,
        )
        # Only the deterministic plan generated for this authorized request is
        # executed. In particular, this never sweeps historical pending plans.
        return self.decide_discussion_plan(
            str(plan["id"]),
            space_id=space_id,
            expected_version=int(plan["version"]),
            accept=True,
            operation_key=f"direct:{request_key}",
            conn=conn,
        )

    @staticmethod
    def _decode_knowledge_plan(row: dict[str, Any]) -> dict[str, Any]:
        row = row_dto(row, timestamps={"created_at", "updated_at"})
        row["payload"] = row.pop("payload_json")
        row["results"] = row.pop("results_json")
        return row

    def _present_knowledge_plan(
        self, plan: dict[str, Any], *, conn=None, prepared_sources=None
    ) -> dict[str, Any]:
        if prepared_sources is None:
            prepared_sources = {} if conn is None else {}
        space = self.store.get_space(int(plan["space_id"]), conn=conn)
        with self.db.connect(conn) as connection:
            source = connection.execute(
                "SELECT thread_id FROM assistant_messages WHERE assistant_messages.workspace_id=%s AND id=%s",
                (
                    self.workspace_id,
                    plan["source_message_id"],
                ),
            ).fetchone()
            plan["thread_id"] = source["thread_id"] if source else None
            for topic in plan["payload"]["topics"]:
                labels = []
                for ref in topic.get("source_refs", []):
                    parts = str(ref).split(":")
                    if len(parts) >= 2 and parts[0] == "video" and parts[1].isdigit():
                        video = connection.execute(
                            "SELECT title FROM videos WHERE videos.workspace_id=%s AND id=%s",
                            (
                                self.workspace_id,
                                int(parts[1]),
                            ),
                        ).fetchone()
                        if video:
                            labels.append(str(video["title"]))
                topic["source_labels"] = labels
            issues = []
            for index, topic in enumerate(plan["payload"]["topics"]):
                if plan["results"].get(str(index), {}).get("status") in {
                    "completed",
                    "ignored",
                }:
                    continue
                local = self._plan_block_issues(
                    connection=connection,
                    space=space,
                    source_message_id=str(plan["source_message_id"]),
                    topics=[topic],
                    conn=connection,
                    prepared_sources=prepared_sources,
                )
                issues.extend(
                    issue.replace("topic[1]", f"topic[{index + 1}]", 1)
                    for issue in local
                )
        plan["confirmable"] = not issues
        plan["validation_issues"] = issues
        plan["issues"] = self._save_issues(issues)
        return plan

    def manage_plan_item(
        self,
        plan_id: str,
        *,
        space_id: int,
        item_index: int,
        action: str,
        expected_version: int,
        operation_key: str,
        conn=None,
    ) -> dict:
        if action not in {"ignore", "restore"}:
            raise ValueError("invalid_plan_action")
        self.store.get_space(space_id, conn=conn)
        with self._transaction(conn, operation_key=operation_key) as connection:
            row = connection.execute(
                "SELECT * FROM assistant_knowledge_plans WHERE assistant_knowledge_plans.workspace_id=%s AND id=%s AND principal_id=%s AND space_id=%s",
                (
                    self.workspace_id,
                    plan_id,
                    self.principal_id,
                    space_id,
                ),
            ).fetchone()
            if row is None:
                raise KeyError(plan_id)
            prior = connection.execute(
                "SELECT result_json FROM assistant_mutation_receipts WHERE assistant_mutation_receipts.workspace_id=%s AND operation_key=%s AND principal_id=%s",
                (
                    self.workspace_id,
                    operation_key,
                    self.principal_id,
                ),
            ).fetchone()
            if prior:
                result = prior["result_json"]
                if result.get("id") != plan_id or result.get("item_action") != {
                    "index": item_index,
                    "action": action,
                }:
                    raise AssistantConflict("operation_key_conflict")
                return result
            plan = self._decode_knowledge_plan(dict(row))
            if (
                plan["status"] not in {"pending", "partial"}
                or int(plan["version"]) != expected_version
            ):
                raise AssistantConflict("knowledge_plan_version_conflict")
            if not 0 <= item_index < len(plan["payload"]["topics"]):
                raise ValueError("item_out_of_range")
            key = str(item_index)
            results = plan["results"]
            # A committed page is authoritative even if the results update was lost.
            receipt_key = (
                f"knowledge-plan:{plan_id}:topic:{item_index}"
                if plan["payload"].get("stable_topic_receipts")
                else f"knowledge-plan:{plan_id}:{expected_version}:{item_index}"
            )
            receipt = connection.execute(
                "SELECT result_json FROM assistant_mutation_receipts WHERE assistant_mutation_receipts.workspace_id=%s AND operation_key=%s AND principal_id=%s",
                (
                    self.workspace_id,
                    receipt_key,
                    self.principal_id,
                ),
            ).fetchone()
            if results.get(key, {}).get("status") == "completed" or receipt:
                raise AssistantConflict("knowledge_topic_already_completed")
            old = results.get(key, {})
            if action == "ignore":
                results[key] = {
                    **old,
                    "status": "ignored",
                    "reason": old.get("reason") or "用户主动忽略未完成项",
                    "before_ignore": old,
                }
            else:
                if old.get("status") != "ignored" or plan["payload"].get(
                    "superseded_by"
                ):
                    raise AssistantConflict("knowledge_item_not_restorable")
                source = connection.execute(
                    "SELECT m.id FROM assistant_messages m JOIN assistant_threads t ON t.id=m.thread_id WHERE m.workspace_id=%s AND m.id=%s AND m.role='user' AND t.principal_id=%s AND t.space_id=%s",
                    (
                        self.workspace_id,
                        plan["source_message_id"],
                        self.principal_id,
                        space_id,
                    ),
                ).fetchone()
                if not source or plan[
                    "source_message_id"
                ] in self._memories().suppressed_source_message_ids(
                    space_id=space_id, conn=connection
                ):
                    raise AssistantConflict("knowledge_plan_authorization_changed")
                space = self.store.get_space(space_id, conn=connection)
                if int(space["scope_version"]) != int(plan["scope_version"]):
                    raise AssistantConflict("knowledge_plan_scope_changed")
                try:
                    problems = self._plan_block_issues(
                        connection=connection,
                        space=space,
                        source_message_id=str(plan["source_message_id"]),
                        topics=[plan["payload"]["topics"][item_index]],
                        conn=connection,
                    )
                except (ValueError, AssistantConflict, KeyError) as exc:
                    problems = [str(exc)]
                results[key] = {
                    **old.get("before_ignore", {}),
                    "status": "failed",
                    "reason": "已恢复；请沿原计划重交未成功主题",
                    "issues": self._save_issues(problems, topic_offset=item_index),
                    "restored_at": utc_now(),
                }
            connection.execute(
                "UPDATE assistant_knowledge_plans SET version=version+1,results_json=%s,updated_at=%s WHERE assistant_knowledge_plans.workspace_id=%s AND id=%s AND version=%s",
                (
                    Jsonb(results),
                    utc_now(),
                    self.workspace_id,
                    plan_id,
                    expected_version,
                ),
            )
            updated = self._present_knowledge_plan(
                self._decode_knowledge_plan(
                    dict(
                        connection.execute(
                            "SELECT * FROM assistant_knowledge_plans WHERE assistant_knowledge_plans.workspace_id=%s AND id=%s",
                            (
                                self.workspace_id,
                                plan_id,
                            ),
                        ).fetchone()
                    )
                ),
                conn=connection,
            )
            updated["item_action"] = {"index": item_index, "action": action}
            connection.execute(
                "INSERT INTO assistant_mutation_receipts(workspace_id,operation_key,principal_id,operation,result_json,created_at) VALUES(%s,%s,%s,'knowledge_item_action',%s,%s)",
                (
                    self.workspace_id,
                    operation_key,
                    self.principal_id,
                    Jsonb(updated),
                    utc_now(),
                ),
            )
            return updated

    def list_discussion_plans(
        self, *, space_id: int, view: str = "all", lightweight: bool = False, conn=None
    ) -> list[dict[str, Any]]:
        self.store.get_space(space_id, conn=conn)
        with self.db.connect(conn) as connection:
            rows = connection.execute(
                """SELECT * FROM assistant_knowledge_plans WHERE assistant_knowledge_plans.workspace_id=%s AND principal_id=%s AND space_id=%s
                ORDER BY created_at DESC""",
                (
                    self.workspace_id,
                    self.principal_id,
                    space_id,
                ),
            ).fetchall()
        plans = [self._decode_knowledge_plan(dict(row)) for row in rows]
        if view == "pending":
            plans = [
                plan
                for plan in plans
                if plan["status"] in {"pending", "partial"}
                and any(
                    plan["results"].get(str(i), {}).get("status")
                    not in {"completed", "ignored"}
                    for i in range(len(plan["payload"]["topics"]))
                )
                and not plan["payload"].get("superseded_by")
            ]
        elif view == "ignored":
            plans = [
                plan
                for plan in plans
                if any(
                    item.get("status") == "ignored" for item in plan["results"].values()
                )
            ]
        if not lightweight:
            return [
                self._present_knowledge_plan(plan, conn=conn) for plan in plans[:30]
            ]
        for plan in plans[:30]:
            payload = plan["payload"]
            plan["confirmable"] = (
                None  # not checked by list; decide revalidates in its transaction
            )
            plan["payload"] = {
                "omitted": payload.get("omitted", []),
                "topics": [
                    {
                        k: topic.get(
                            k, [] if k in {"cross_references", "omitted"} else ""
                        )
                        for k in ("title", "purpose", "cross_references", "omitted")
                    }
                    for topic in payload["topics"]
                ],
            }
            plan["issues"] = []
        return plans[:30]

    def plan_source_options(
        self, plan_id: str, *, space_id: int, query: str = "", conn=None
    ) -> list[dict[str, Any]]:
        """Offer selected and task encountered sources; optional scoped title search."""
        space = self.store.get_space(space_id, conn=conn)
        scope = self._scope(space)
        with self.db.connect(conn) as connection:
            row = connection.execute(
                "SELECT source_message_id,payload_json FROM assistant_knowledge_plans WHERE assistant_knowledge_plans.workspace_id=%s AND id=%s AND principal_id=%s AND space_id=%s",
                (
                    self.workspace_id,
                    plan_id,
                    self.principal_id,
                    space_id,
                ),
            ).fetchone()
            if row is None:
                raise KeyError(plan_id)
            payload = row["payload_json"]
            selected = {
                str(ref)
                for topic in payload["topics"]
                for block in topic.get("blocks") or []
                for ref in block.get("source_refs") or []
            }
            source_message = connection.execute(
                "SELECT run_id,thread_id FROM assistant_messages WHERE assistant_messages.workspace_id=%s AND id=%s",
                (
                    self.workspace_id,
                    row["source_message_id"],
                ),
            ).fetchone()
            refs = set(selected)
            if source_message and source_message["run_id"]:
                for call in connection.execute(
                    "SELECT name,result_json FROM assistant_tool_calls WHERE assistant_tool_calls.workspace_id=%s AND run_id=%s AND status='completed' ORDER BY ordinal",
                    (
                        self.workspace_id,
                        source_message["run_id"],
                    ),
                ):
                    if call["name"] not in {
                        "collection_search",
                        "collection_read",
                        "knowledge_read",
                    }:
                        continue
                    try:
                        result = call["result_json"] or {}
                    except ValueError:
                        continue
                    refs.update(
                        str(ref)
                        for ref in result.get("source_refs") or []
                        if str(ref).startswith("video:")
                    )
                    for item in result.get("items") or []:
                        if isinstance(item, dict):
                            refs.update(
                                str(ref)
                                for ref in item.get("source_refs") or []
                                if str(ref).startswith("video:")
                            )
        if source_message:
            note = (
                self.store.get_thread(str(source_message["thread_id"])).get("task_note")
                or {}
            )
            if note.get("status") == "active" and note.get("usable") is not False:
                for material in (note.get("searched_scope_and_material_refs") or [])[
                    -12:
                ]:
                    refs.update(
                        str(ref)
                        for ref in material.get("source_refs") or []
                        if str(ref).startswith("video:")
                    )
        if query.strip():
            found = self.sources.search(
                call_id="plan-source-search",
                scope=scope,
                query=query.strip()[:120],
                mode="metadata",
                limit=10,
                scope_version=int(space["scope_version"]),
            )
            with self.db.connect(conn) as connection:
                for raw_ref in found.source_refs:
                    parts = str(raw_ref).split(":")
                    if len(parts) < 2 or parts[0] != "video" or not parts[1].isdigit():
                        continue
                    head = connection.execute(
                        "SELECT current_revision FROM assistant_source_heads WHERE assistant_source_heads.workspace_id=%s AND principal_id=%s AND video_id=%s",
                        (
                            self.workspace_id,
                            self.principal_id,
                            int(parts[1]),
                        ),
                    ).fetchone()
                    if head:
                        refs.add(f"video:{parts[1]}:{head['current_revision']}")
        options = []
        with self.db.connect(conn) as connection:
            for ref in sorted(refs):
                parts = ref.split(":")
                if (
                    len(parts) != 3
                    or not parts[1].isdigit()
                    or not self.sources.source_refs_visible([ref], scope, conn=conn)
                ):
                    continue
                head = connection.execute(
                    "SELECT current_revision FROM assistant_source_heads WHERE assistant_source_heads.workspace_id=%s AND principal_id=%s AND video_id=%s",
                    (
                        self.workspace_id,
                        self.principal_id,
                        int(parts[1]),
                    ),
                ).fetchone()
                if not head or head["current_revision"] != parts[2]:
                    continue
                video = connection.execute(
                    "SELECT title,uploader FROM videos WHERE videos.workspace_id=%s AND id=%s",
                    (
                        self.workspace_id,
                        int(parts[1]),
                    ),
                ).fetchone()
                if video:
                    options.append(
                        {
                            "source_ref": ref,
                            "title": str(video["title"]),
                            "uploader": str(video["uploader"] or ""),
                            "selected": ref in selected,
                            "view": "当前可用收藏",
                        }
                    )
        return sorted(options, key=lambda item: (not item["selected"], item["title"]))[
            :16
        ]

    def plan_selected_source_statuses(
        self, plan_id: str, *, space_id: int, conn=None
    ) -> list[dict[str, str]]:
        """Inspect only refs already bound to this plan, without replacing their revisions."""
        space = self.store.get_space(space_id, conn=conn)
        scope = self._scope(space)
        with self.db.connect(conn) as connection:
            row = connection.execute(
                "SELECT payload_json FROM assistant_knowledge_plans WHERE assistant_knowledge_plans.workspace_id=%s AND id=%s AND principal_id=%s AND space_id=%s",
                (
                    self.workspace_id,
                    plan_id,
                    self.principal_id,
                    space_id,
                ),
            ).fetchone()
            if row is None:
                raise KeyError(plan_id)
            payload = row["payload_json"]
            selected = list(
                dict.fromkeys(
                    str(ref)
                    for topic in payload["topics"]
                    for block in topic.get("blocks") or []
                    for ref in block.get("source_refs") or []
                )
            )
            statuses = []
            for ref in selected[:64]:
                parts = ref.split(":")
                item = {"source_ref": ref, "title": "已绑定来源", "status": "invalid"}
                if len(parts) == 3 and parts[0] == "video" and parts[1].isdigit():
                    head = connection.execute(
                        "SELECT current_revision FROM assistant_source_heads WHERE assistant_source_heads.workspace_id=%s AND principal_id=%s AND video_id=%s",
                        (
                            self.workspace_id,
                            self.principal_id,
                            int(parts[1]),
                        ),
                    ).fetchone()
                    if head:
                        video = connection.execute(
                            "SELECT title FROM videos WHERE videos.workspace_id=%s AND id=%s",
                            (
                                self.workspace_id,
                                int(parts[1]),
                            ),
                        ).fetchone()
                        if video:
                            item["title"] = str(video["title"])
                        if str(head["current_revision"]) != parts[2]:
                            item["status"] = "revision_changed"
                        elif not self.sources.source_refs_visible(
                            [ref], scope, conn=conn
                        ):
                            item["status"] = "out_of_scope"
                        else:
                            item["status"] = "available"
                statuses.append(item)
        return statuses

    def legacy_repair_input(self, args: dict, *, space_id: int, conn=None) -> dict:
        """Decode persisted old calls/UI payloads, never a second write implementation."""
        with self.db.connect(conn) as c:
            row = c.execute(
                "SELECT * FROM assistant_knowledge_plans WHERE assistant_knowledge_plans.workspace_id=%s AND id=%s AND principal_id=%s AND space_id=%s",
                (
                    self.workspace_id,
                    args["plan_id"],
                    self.principal_id,
                    space_id,
                ),
            ).fetchone()
            if row is None:
                raise ValueError("plan_not_found")
            plan = self._decode_knowledge_plan(dict(row))
        topics = json.loads(json.dumps(plan["payload"]["topics"]))
        touched = set()
        for correction in args.get("corrections") or []:
            match = re.fullmatch(
                r"topics\[(\d+)\](?:\.blocks\[(\d+)\])?\.([a-z_]+)", correction["path"]
            )
            if not match:
                raise ValueError("legacy_repair_requires_topic_resubmission")
            ti = int(match[1])
            bi = int(match[2]) if match[2] is not None else None
            if ti >= len(topics) or bi is not None and bi >= len(topics[ti]["blocks"]):
                raise ValueError("invalid_repair_path")
            target = topics[ti] if bi is None else topics[ti]["blocks"][bi]
            target[match[3]] = correction["value"]
            touched.add(ti)
        return {
            "plan_id": args["plan_id"],
            "expected_version": args["expected_version"],
            "replacements": [
                {
                    "index": ti,
                    "topic": {
                        k: v
                        for k, v in topics[ti].items()
                        if k not in {"page_id", "source_refs", "source_labels"}
                    },
                }
                for ti in sorted(touched)
            ],
        }

    def repair_discussion_plan(
        self,
        plan_id: str,
        *,
        space_id: int,
        expected_version: int,
        corrections: list[dict],
        request: dict,
        repair_count: int = 0,
        operation_key: str,
        conn=None,
    ) -> dict:
        # Compatibility for old persisted/UI calls only; all validation is topic-level.
        converted = self.legacy_repair_input(
            {
                "plan_id": plan_id,
                "expected_version": expected_version,
                "corrections": corrections,
            },
            space_id=space_id,
            conn=conn,
        )
        return self.replace_discussion_topics(
            plan_id,
            space_id=space_id,
            expected_version=expected_version,
            replacements=converted["replacements"],
            request=request,
            operation_key=operation_key,
            conn=conn,
        )

    def replace_discussion_topics(
        self,
        plan_id: str,
        *,
        space_id: int,
        expected_version: int,
        replacements: list[dict],
        request: dict,
        operation_key: str,
        conn=None,
    ) -> dict:
        from shiliu.assistant.tools import KnowledgePlanTopic

        with self._transaction(conn, operation_key=operation_key) as c:
            receipt = c.execute(
                "SELECT result_json FROM assistant_mutation_receipts WHERE assistant_mutation_receipts.workspace_id=%s AND operation_key=%s AND principal_id=%s",
                (
                    self.workspace_id,
                    operation_key,
                    self.principal_id,
                ),
            ).fetchone()
            if receipt:
                return receipt["result_json"]
            row = c.execute(
                "SELECT * FROM assistant_knowledge_plans WHERE assistant_knowledge_plans.workspace_id=%s AND id=%s AND principal_id=%s AND space_id=%s",
                (
                    self.workspace_id,
                    plan_id,
                    self.principal_id,
                    space_id,
                ),
            ).fetchone()
            if row is None:
                raise ValueError("plan_not_found")
            plan = self._decode_knowledge_plan(dict(row))
            if plan["status"] not in {"pending", "partial"}:
                raise AssistantConflict("knowledge_plan_not_repairable")
            if plan["version"] != expected_version:
                raise AssistantConflict("knowledge_plan_version_conflict")
            original = c.execute(
                "SELECT thread_id FROM assistant_messages WHERE assistant_messages.workspace_id=%s AND id=%s",
                (
                    self.workspace_id,
                    plan["source_message_id"],
                ),
            ).fetchone()
            current_id = (
                request.get("last_repair_message_id") or request["source_message_id"]
            )
            current = c.execute(
                "SELECT m.thread_id FROM assistant_messages m JOIN assistant_threads t ON t.id=m.thread_id WHERE m.workspace_id=%s AND m.id=%s AND m.role='user' AND t.principal_id=%s AND t.space_id=%s",
                (
                    self.workspace_id,
                    current_id,
                    self.principal_id,
                    space_id,
                ),
            ).fetchone()
            if not current or current["thread_id"] != original["thread_id"]:
                raise AssistantConflict("knowledge_plan_request_mismatch")
            if (
                self.store.get_space(space_id, conn=c)["scope_version"]
                != plan["scope_version"]
            ):
                raise AssistantConflict("knowledge_plan_scope_changed")
            payload = json.loads(json.dumps(plan["payload"]))
            payload.setdefault(
                "original_topics", json.loads(json.dumps(payload["topics"]))
            )
            touched = set()
            changed = False
            for replacement in replacements:
                ti = replacement["index"]
                if ti in touched or ti < 0 or ti >= len(payload["topics"]):
                    raise ValueError("invalid_topic_index")
                touched.add(ti)
                key = (
                    f"knowledge-plan:{plan_id}:topic:{ti}"
                    if payload.get("stable_topic_receipts")
                    else f"knowledge-plan:{plan_id}:{expected_version}:{ti}"
                )
                if c.execute(
                    "SELECT 1 FROM assistant_mutation_receipts WHERE assistant_mutation_receipts.workspace_id=%s AND operation_key=%s AND principal_id=%s",
                    (
                        self.workspace_id,
                        key,
                        self.principal_id,
                    ),
                ).fetchone() or plan["results"].get(str(ti), {}).get("status") in {
                    "completed",
                    "ignored",
                }:
                    raise AssistantConflict("knowledge_topic_already_completed")
                topic = KnowledgePlanTopic.model_validate(
                    replacement["topic"]
                ).model_dump(mode="json")
                before = payload["topics"][ti]
                if self._normalize_title(topic["title"]) != self._normalize_title(
                    before["title"]
                ):
                    raise AssistantConflict(
                        "knowledge_topic_target_changed_use_new_edit"
                    )
                normalized_before = KnowledgePlanTopic.model_validate(
                    {
                        k: v
                        for k, v in before.items()
                        if k not in {"page_id", "source_refs", "source_labels"}
                    }
                ).model_dump(mode="json")
                changed = changed or topic != normalized_before
                topic["page_id"] = before.get("page_id")
                topic["source_refs"] = sorted(
                    {r for b in topic["blocks"] for r in b.get("source_refs") or []}
                )
                payload["topics"][ti] = topic
            if (
                not changed
                and payload.get("save_request", {}).get("last_repair_message_id")
                == current_id
            ):
                return self._present_knowledge_plan(plan, conn=c)
            payload["save_request"] = {
                **payload.get("save_request", {}),
                "last_repair_message_id": current_id,
            }
            self._preserve_notification_plan(c, plan, payload)
            c.execute(
                "UPDATE assistant_knowledge_plans SET version=version+1,payload_json=%s,updated_at=%s WHERE assistant_knowledge_plans.workspace_id=%s AND id=%s AND version=%s",
                (
                    Jsonb(payload),
                    utc_now(),
                    self.workspace_id,
                    plan_id,
                    expected_version,
                ),
            )
            updated = self._present_knowledge_plan(
                self._decode_knowledge_plan(
                    dict(
                        c.execute(
                            "SELECT * FROM assistant_knowledge_plans WHERE assistant_knowledge_plans.workspace_id=%s AND id=%s",
                            (
                                self.workspace_id,
                                plan_id,
                            ),
                        ).fetchone()
                    )
                ),
                conn=c,
            )
            c.execute(
                "INSERT INTO assistant_mutation_receipts(workspace_id,operation_key,principal_id,operation,result_json,created_at) VALUES(%s,%s,%s,'knowledge_plan_replace',%s,%s)",
                (
                    self.workspace_id,
                    operation_key,
                    self.principal_id,
                    Jsonb(updated),
                    utc_now(),
                ),
            )
            self._notify_plan(c, updated, previous=plan)
            return updated

    def revise_discussion_plan(
        self,
        plan_id: str,
        *,
        space_id: int,
        expected_version: int,
        topics: list[dict[str, Any]],
        omitted: list[str],
        operation_key: str,
        conn=None,
    ) -> dict[str, Any]:
        if not 1 <= len(topics) <= 6:
            raise ValueError("invalid_knowledge_plan")
        space = self.store.get_space(space_id, conn=conn)
        with self._transaction(conn, operation_key=operation_key) as connection:
            receipt = connection.execute(
                "SELECT result_json FROM assistant_mutation_receipts WHERE assistant_mutation_receipts.workspace_id=%s AND operation_key=%s AND principal_id=%s",
                (
                    self.workspace_id,
                    operation_key,
                    self.principal_id,
                ),
            ).fetchone()
            if receipt:
                return receipt["result_json"]
            row = connection.execute(
                "SELECT * FROM assistant_knowledge_plans WHERE assistant_knowledge_plans.workspace_id=%s AND id=%s AND principal_id=%s AND space_id=%s",
                (
                    self.workspace_id,
                    plan_id,
                    self.principal_id,
                    space_id,
                ),
            ).fetchone()
            if row is None:
                raise KeyError(plan_id)
            plan = self._decode_knowledge_plan(dict(row))
            if plan["status"] != "pending" or int(plan["version"]) != expected_version:
                raise AssistantConflict("knowledge_plan_version_conflict")
            if int(plan["scope_version"]) != int(space["scope_version"]):
                raise AssistantConflict("knowledge_plan_scope_changed")
            if plan["payload"].get("stable_topic_receipts") and len(topics) != len(
                plan["payload"]["topics"]
            ):
                raise ValueError("knowledge_topic_positions_fixed")
            names = set()
            prepared = []
            for item in topics:
                title, purpose = (
                    str(item.get("title") or "").strip(),
                    str(item.get("purpose") or "").strip(),
                )
                blocks = item.get("blocks") or []
                normalized = self._normalize_title(title)
                if (
                    not normalized
                    or normalized in names
                    or len(title) > 120
                    or not purpose
                    or len(purpose) > 600
                    or not 1 <= len(blocks) <= 8
                ):
                    raise ValueError("invalid_knowledge_plan_topic")
                names.add(normalized)
                refs = sorted(
                    {
                        str(ref)
                        for block in blocks
                        for ref in block.get("source_refs", [])
                    }
                )
                if refs and not self.sources.source_refs_visible(
                    refs, self._scope(space), conn=conn
                ):
                    raise ValueError("source_out_of_scope")
                page = connection.execute(
                    """SELECT id,version FROM assistant_wiki_pages WHERE assistant_wiki_pages.workspace_id=%s AND principal_id=%s AND space_id=%s
                    AND normalized_title=%s AND status='active'""",
                    (
                        self.workspace_id,
                        self.principal_id,
                        space_id,
                        normalized,
                    ),
                ).fetchone()
                prepared.append(
                    {
                        "title": title,
                        "purpose": purpose,
                        "blocks": blocks,
                        "source_refs": refs,
                        "cross_references": item.get("cross_references") or [],
                        "omitted": item.get("omitted") or [],
                        "page_id": str(page["id"]) if page else None,
                        "expected_version": int(page["version"]) if page else None,
                    }
                )
            issues = self._plan_block_issues(
                connection=connection,
                space=space,
                source_message_id=str(plan["source_message_id"]),
                topics=prepared,
                conn=connection,
            )
            if issues:
                raise ValueError(
                    "knowledge_plan_not_confirmable:" + ";".join(issues[:12])
                )
            self._preserve_notification_plan(
                connection,
                plan,
                {**plan["payload"], "topics": prepared, "omitted": omitted[:20]},
            )
            connection.execute(
                """UPDATE assistant_knowledge_plans SET version=version+1,payload_json=%s,updated_at=%s
                WHERE assistant_knowledge_plans.workspace_id=%s AND id=%s AND version=%s AND status='pending'""",
                (
                    Jsonb(
                        {**plan["payload"], "topics": prepared, "omitted": omitted[:20]}
                    ),
                    utc_now(),
                    self.workspace_id,
                    plan_id,
                    expected_version,
                ),
            )
            updated = self._present_knowledge_plan(
                self._decode_knowledge_plan(
                    dict(
                        connection.execute(
                            "SELECT * FROM assistant_knowledge_plans WHERE assistant_knowledge_plans.workspace_id=%s AND id=%s",
                            (
                                self.workspace_id,
                                plan_id,
                            ),
                        ).fetchone()
                    )
                ),
                conn=connection,
            )
            self._notify_plan(connection, updated, previous=plan)
            connection.execute(
                """INSERT INTO assistant_mutation_receipts(workspace_id,operation_key,principal_id,operation,result_json,created_at)
                VALUES(%s,%s,%s,'knowledge_plan_revise',%s,%s)""",
                (
                    self.workspace_id,
                    operation_key,
                    self.principal_id,
                    Jsonb(updated),
                    utc_now(),
                ),
            )
        return updated

    def decide_discussion_plan(
        self,
        plan_id: str,
        *,
        space_id: int,
        expected_version: int,
        accept: bool,
        operation_key: str,
        conn=None,
        prepared_sources=None,
    ) -> dict[str, Any]:
        # Claim the exact version before any page write. A pending plan can be
        # revised or rejected only until this transaction commits.
        if prepared_sources is None:
            prepared_sources = (
                self._prepare_sources_for_write(space_id=space_id)
                if conn is None
                else {}
            )
        with self.db.connect(conn) as connection:
            row = connection.execute(
                "SELECT * FROM assistant_knowledge_plans WHERE assistant_knowledge_plans.workspace_id=%s AND id=%s AND principal_id=%s AND space_id=%s",
                (
                    self.workspace_id,
                    plan_id,
                    self.principal_id,
                    space_id,
                ),
            ).fetchone()
            if row is None:
                raise KeyError(plan_id)
            observed = self._decode_knowledge_plan(dict(row))
            if int(observed["version"]) != expected_version:
                raise AssistantConflict("knowledge_plan_version_conflict")
        space = self.store.get_space(space_id, conn=conn)
        if int(space["scope_version"]) != int(observed["scope_version"]):
            raise AssistantConflict("knowledge_plan_scope_changed")
        with self._transaction(conn, operation_key=operation_key) as connection:
            row = connection.execute(
                "SELECT * FROM assistant_knowledge_plans WHERE assistant_knowledge_plans.workspace_id=%s AND id=%s AND principal_id=%s AND space_id=%s",
                (
                    self.workspace_id,
                    plan_id,
                    self.principal_id,
                    space_id,
                ),
            ).fetchone()
            if row is None:
                raise KeyError(plan_id)
            plan = self._decode_knowledge_plan(dict(row))
            if int(plan["version"]) != expected_version:
                raise AssistantConflict("knowledge_plan_version_conflict")
            current_scope = connection.execute(
                "SELECT scope_version FROM assistant_spaces WHERE assistant_spaces.workspace_id=%s AND id=%s",
                (
                    self.workspace_id,
                    space_id,
                ),
            ).fetchone()
            if current_scope is None or int(current_scope["scope_version"]) != int(
                plan["scope_version"]
            ):
                raise AssistantConflict("knowledge_plan_scope_changed")
            if not accept:
                if plan["status"] == "pending":
                    changed = connection.execute(
                        """UPDATE assistant_knowledge_plans SET status='rejected',updated_at=%s
                        WHERE assistant_knowledge_plans.workspace_id=%s AND id=%s AND version=%s AND status='pending'""",
                        (
                            utc_now(),
                            self.workspace_id,
                            plan_id,
                            expected_version,
                        ),
                    )
                    if changed.rowcount != 1:
                        raise AssistantConflict("knowledge_plan_state_changed")
                    plan["status"] = "rejected"
                    plan["updated_at"] = utc_now()
                    identity = self._notify_plan(connection, plan)
                    if identity:
                        connection.execute(
                            "UPDATE assistant_notifications SET activity_at=%s WHERE workspace_id=%s AND principal_id=%s AND id=%s",
                            (
                                plan["updated_at"],
                                self.workspace_id,
                                self.principal_id,
                                identity,
                            ),
                        )
                    return plan
                if plan["status"] == "rejected":
                    return plan
                raise AssistantConflict("knowledge_plan_already_accepted")
            if plan["status"] == "rejected":
                raise AssistantConflict("knowledge_plan_rejected")
            if plan["status"] == "completed":
                return plan
            if plan["status"] == "pending":
                issues = self._plan_block_issues(
                    connection=connection,
                    space=space,
                    source_message_id=str(plan["source_message_id"]),
                    topics=plan["payload"]["topics"],
                    conn=connection,
                    prepared_sources=prepared_sources,
                )
                blocking = [
                    issue
                    for issue in issues
                    if not issue.endswith(
                        (":wiki_version_conflict", ":wiki_page_missing")
                    )
                ]
                if blocking and not plan["payload"].get("direct_authorized"):
                    raise AssistantConflict(
                        "knowledge_plan_not_confirmable:" + ";".join(blocking[:12])
                    )
                changed = connection.execute(
                    """UPDATE assistant_knowledge_plans SET status='partial',updated_at=%s
                    WHERE assistant_knowledge_plans.workspace_id=%s AND id=%s AND version=%s AND status='pending'""",
                    (
                        utc_now(),
                        self.workspace_id,
                        plan_id,
                        expected_version,
                    ),
                )
                if changed.rowcount != 1:
                    raise AssistantConflict("knowledge_plan_state_changed")
                plan["status"] = "partial"
                self._notify_plan(connection, plan)
            elif plan["status"] != "partial":
                raise AssistantConflict("knowledge_plan_state_changed")
        for index, item in enumerate(plan["payload"]["topics"]):
            key = str(index)
            with self.db.connect(conn) as connection:
                live = self._decode_knowledge_plan(
                    dict(
                        connection.execute(
                            "SELECT * FROM assistant_knowledge_plans WHERE assistant_knowledge_plans.workspace_id=%s AND id=%s",
                            (
                                self.workspace_id,
                                plan_id,
                            ),
                        ).fetchone()
                    )
                )
            if live["results"].get(key, {}).get("status") in {"completed", "ignored"}:
                continue
            page_key = (
                f"knowledge-plan:{plan_id}:topic:{index}"
                if plan["payload"].get("stable_topic_receipts")
                else f"knowledge-plan:{plan_id}:{expected_version}:{index}"
            )
            try:
                with self.db.connect(conn) as connection:
                    receipt = connection.execute(
                        "SELECT result_json FROM assistant_mutation_receipts WHERE assistant_mutation_receipts.workspace_id=%s AND operation_key=%s AND principal_id=%s",
                        (
                            self.workspace_id,
                            page_key,
                            self.principal_id,
                        ),
                    ).fetchone()
                if receipt:
                    page = receipt["result_json"]
                    outcome = {
                        "status": "completed",
                        "page_id": page["id"],
                        "version": page["version"],
                    }
                else:
                    outcome = None
                if not receipt and plan["payload"].get("direct_authorized"):
                    with self.db.connect(conn) as connection:
                        item_issues = self._plan_block_issues(
                            connection=connection,
                            space=space,
                            source_message_id=str(plan["source_message_id"]),
                            topics=[item],
                            conn=connection,
                            prepared_sources=prepared_sources,
                        )
                    if item_issues:
                        raise ValueError(
                            "knowledge_topic_invalid:" + ";".join(item_issues[:8])
                        )
                if outcome is None:
                    page = self.save_discussion(
                        space_id=space_id,
                        title=item["title"],
                        purpose=item["purpose"],
                        blocks=item["blocks"],
                        expected_version=item["expected_version"],
                        source_message_id=plan["source_message_id"],
                        operation_key=page_key,
                        authorized_plan_id=plan_id,
                        authorized_plan_version=expected_version,
                        conn=conn,
                        prepared_sources=prepared_sources,
                    )
                    outcome = {
                        "status": "completed",
                        "page_id": page["id"],
                        "version": page["version"],
                    }
            except (ValueError, AssistantConflict, KeyError) as exc:
                failures = str(exc).removeprefix("knowledge_topic_invalid:").split(";")
                try:
                    with self.db.connect(conn) as connection:
                        current_issues = self._plan_block_issues(
                            connection=connection,
                            space=space,
                            source_message_id=str(plan["source_message_id"]),
                            topics=[item],
                            conn=connection,
                            prepared_sources=prepared_sources,
                        )
                    failures = current_issues or failures
                except (ValueError, AssistantConflict, KeyError):
                    pass
                outcome = {
                    "status": "failed",
                    "reason": str(exc),
                    "issues": self._save_issues(failures, topic_offset=index),
                }
            with self._transaction(conn, operation_key=operation_key) as connection:
                current = self._decode_knowledge_plan(
                    dict(
                        connection.execute(
                            "SELECT * FROM assistant_knowledge_plans WHERE assistant_knowledge_plans.workspace_id=%s AND id=%s",
                            (
                                self.workspace_id,
                                plan_id,
                            ),
                        ).fetchone()
                    )
                )
                if int(current["version"]) != expected_version or current[
                    "status"
                ] not in {"partial", "completed"}:
                    raise AssistantConflict("knowledge_plan_state_changed")
                results = dict(current["results"])
                if results.get(key, {}).get("status") != "completed":
                    results[key] = outcome
                status = (
                    "completed"
                    if all(
                        results.get(str(i), {}).get("status") == "completed"
                        for i in range(len(plan["payload"]["topics"]))
                    )
                    else "partial"
                )
                connection.execute(
                    """UPDATE assistant_knowledge_plans SET results_json=%s,status=%s,updated_at=%s
                    WHERE assistant_knowledge_plans.workspace_id=%s AND id=%s AND version=%s""",
                    (
                        Jsonb(results),
                        status,
                        utc_now(),
                        self.workspace_id,
                        plan_id,
                        expected_version,
                    ),
                )
                if (
                    plan["payload"].get("direct_authorized")
                    and outcome.get("status") == "failed"
                ):
                    self._notify_plan(
                        connection,
                        {
                            **current,
                            "results": results,
                            "status": status,
                            "updated_at": utc_now(),
                        },
                    )
        with self.db.connect(conn) as connection:
            latest = self._decode_knowledge_plan(
                dict(
                    connection.execute(
                        "SELECT * FROM assistant_knowledge_plans WHERE assistant_knowledge_plans.workspace_id=%s AND id=%s",
                        (
                            self.workspace_id,
                            plan_id,
                        ),
                    ).fetchone()
                )
            )
        return {**latest, "operation_key": operation_key}

    def _personal_dependency_current(
        self,
        connection: Any,
        *,
        space_id: int,
        memory_id: str,
        memory_version: int,
        source_message_id: str | None,
        conn=None,
    ) -> bool:
        conn = connection if conn is None else conn
        row = connection.execute(
            "SELECT * FROM assistant_memories WHERE assistant_memories.workspace_id=%s AND id=%s AND principal_id=%s",
            (
                self.workspace_id,
                memory_id,
                self.principal_id,
            ),
        ).fetchone()
        if row is None:
            return False
        memory = dict(row)
        if (
            memory["status"] != "active"
            or int(memory["version"]) != memory_version
            or not MemoryService._is_currently_valid(memory)
            or not (
                memory["scope_kind"] == "user"
                or (
                    memory["scope_kind"] == "space"
                    and str(memory["scope_id"]) == str(space_id)
                )
            )
        ):
            return False
        if source_message_id:
            message = connection.execute(
                """SELECT 1 FROM assistant_messages m JOIN assistant_threads t ON t.id=m.thread_id
                WHERE m.workspace_id=%s AND m.id=%s AND m.role='user' AND t.principal_id=%s AND t.space_id=%s""",
                (
                    self.workspace_id,
                    source_message_id,
                    self.principal_id,
                    space_id,
                ),
            ).fetchone()
            if message is None:
                return False
            suppressions = connection.execute(
                """SELECT source_message_ids_json FROM assistant_memory_suppressions
                WHERE assistant_memory_suppressions.workspace_id=%s AND principal_id=%s AND (scope_kind='user' OR (scope_kind='space' AND scope_id=%s))""",
                (
                    self.workspace_id,
                    self.principal_id,
                    str(space_id),
                ),
            ).fetchall()
            if any(
                source_message_id in (item["source_message_ids_json"] or [])
                for item in suppressions
            ):
                return False
        return True

    def changes(self, page_id: str, *, conn=None) -> list[dict[str, Any]]:
        self.get_page(page_id, include_hidden=True, conn=conn)
        with self.db.connect(conn) as connection:
            rows = connection.execute(
                """
                SELECT version, operation, summary, actor, created_at
                FROM assistant_wiki_changes WHERE assistant_wiki_changes.workspace_id=%s AND page_id=%s ORDER BY version DESC
                """,
                (
                    self.workspace_id,
                    page_id,
                ),
            ).fetchall()
            states = {
                int(row["version"])
                for row in connection.execute(
                    "SELECT version FROM assistant_wiki_operation_states WHERE assistant_wiki_operation_states.workspace_id=%s AND page_id=%s",
                    (
                        self.workspace_id,
                        page_id,
                    ),
                ).fetchall()
            }
        return [
            {
                **row_dto(row, timestamps={"created_at"}),
                "can_revert": int(row["version"]) in states
                or int(row["version"]) + 1 in states,
            }
            for row in rows
        ]

    def merge_pages(
        self,
        source_page_id: str,
        target_page_id: str,
        *,
        space_id: int,
        source_version: int,
        target_version: int,
        operation_key: str,
        accept_conflict: bool = False,
        _notification_proposal=None,
        _connection: Any | None = None,
        conn=None,
        prepared_sources=None,
    ) -> dict[str, Any]:
        """Merge two explicit same-scope topics, or hold a concrete manual conflict."""
        if prepared_sources is None:
            prepared_sources = (
                self._prepare_sources_for_write(space_id=space_id)
                if conn is None
                else {}
            )
        if source_page_id == target_page_id:
            raise ValueError("same_wiki_page")
        now = utc_now()
        with self._transaction(
            _connection,
            operation_key=operation_key,
            page_ids=[source_page_id, target_page_id],
        ) as connection:
            receipt = connection.execute(
                "SELECT result_json FROM assistant_mutation_receipts WHERE assistant_mutation_receipts.workspace_id=%s AND operation_key=%s AND principal_id=%s",
                (
                    self.workspace_id,
                    operation_key,
                    self.principal_id,
                ),
            ).fetchone()
            if receipt is not None:
                return receipt["result_json"]
            rows = connection.execute(
                """SELECT * FROM assistant_wiki_pages WHERE assistant_wiki_pages.workspace_id=%s AND id IN (%s,%s) AND principal_id=%s
                AND space_id=%s AND status='active'""",
                (
                    self.workspace_id,
                    source_page_id,
                    target_page_id,
                    self.principal_id,
                    space_id,
                ),
            ).fetchall()
            by_id = {str(row["id"]): self._decode_page(dict(row)) for row in rows}
            if set(by_id) != {source_page_id, target_page_id}:
                raise KeyError("wiki_merge_page_missing")
            source, target = by_id[source_page_id], by_id[target_page_id]
            if (
                int(source["version"]) != source_version
                or int(target["version"]) != target_version
            ):
                raise AssistantConflict("wiki_version_conflict")
            visible_source = self._visible_page(
                source, conn=conn, snapshot_cache=prepared_sources
            )
            visible_target = self._visible_page(
                target, conn=conn, snapshot_cache=prepared_sources
            )
            if not visible_source["blocks"]:
                raise AssistantConflict("wiki_source_has_no_current_content")
            manual_target = {
                str(block["heading"]).strip().casefold(): block
                for block in visible_target["blocks"]
                if block.get("manual_lock")
            }
            conflicts = [
                block
                for block in visible_source["blocks"]
                if block.get("manual_lock")
                and str(block["heading"]).strip().casefold() in manual_target
                and str(block["markdown"])
                != str(
                    manual_target[str(block["heading"]).strip().casefold()]["markdown"]
                )
            ]
            fingerprint = hashlib.sha256(
                json.dumps(
                    {
                        "source": source_page_id,
                        "target": target_page_id,
                        "source_version": source_version,
                        "target_version": target_version,
                        "conflicts": [block["stable_id"] for block in conflicts],
                    },
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            if conflicts and not accept_conflict:
                proposal = connection.execute(
                    """SELECT id,status FROM assistant_wiki_proposals
                    WHERE assistant_wiki_proposals.workspace_id=%s AND principal_id=%s AND space_id=%s AND kind='merge'
                      AND target_page_id=%s AND input_fingerprint=%s""",
                    (
                        self.workspace_id,
                        self.principal_id,
                        space_id,
                        target_page_id,
                        fingerprint,
                    ),
                ).fetchone()
                if proposal is None:
                    proposal_id = f"awprop_{uuid.uuid4().hex}"
                    self._notify_proposal(
                        connection,
                        dict(
                            connection.execute(
                                "INSERT INTO assistant_wiki_proposals(workspace_id,\n                            id,principal_id,space_id,kind,source_page_id,target_page_id,\n                            source_version,target_version,input_fingerprint,payload_json,\n                            status,created_at,updated_at\n                        ) VALUES(%s,%s,%s,%s,'merge',%s,%s,%s,%s,%s,%s,'pending',%s,%s) RETURNING *",
                                (
                                    self.workspace_id,
                                    proposal_id,
                                    self.principal_id,
                                    space_id,
                                    source_page_id,
                                    target_page_id,
                                    source_version,
                                    target_version,
                                    fingerprint,
                                    Jsonb(
                                        {
                                            "conflict_block_ids": [
                                                block["stable_id"]
                                                for block in conflicts
                                            ]
                                        }
                                    ),
                                    now,
                                    now,
                                ),
                            ).fetchone()
                        ),
                    )
                    status = "pending"
                else:
                    proposal_id, status = str(proposal["id"]), str(proposal["status"])
                return {
                    "status": status,
                    "proposal_id": proposal_id,
                    "reason": "manual_content_conflict",
                }
            source_before = self._operation_state(connection, source_page_id, conn=conn)
            target_before = self._operation_state(connection, target_page_id, conn=conn)
            self._assert_lifecycle(target, visible_source["blocks"])
            target_blocks = list(target["blocks"])
            for tomb in source["blocks"]:
                if tomb.get("deleted"):
                    carried = {**tomb, "lifecycle_version": target_version + 1}
                    if any(b["stable_id"] == tomb["stable_id"] for b in target_blocks):
                        carried["deleted_stable_id"] = tomb["stable_id"]
                        carried["stable_id"] = (
                            f"tomb_{source_page_id}_{tomb['stable_id']}"
                        )
                    target_blocks.append(carried)
            target_ids = {str(block["stable_id"]) for block in target_blocks}
            mapped_ids: dict[str, str] = {}
            for block in visible_source["blocks"]:
                candidate = dict(block)
                old_id = str(candidate["stable_id"])
                if old_id in target_ids:
                    existing = next(
                        item for item in target_blocks if item["stable_id"] == old_id
                    )
                    if all(
                        existing.get(field) == candidate.get(field)
                        for field in (
                            "markdown",
                            "heading",
                            "source_refs",
                            "assessment",
                        )
                    ):
                        mapped_ids[old_id] = old_id
                        continue
                    candidate["stable_id"] = f"wblock_merge_{uuid.uuid4().hex[:20]}"
                if old_id in {str(item["stable_id"]) for item in conflicts}:
                    candidate["relation"] = "condition_difference"
                mapped_ids[old_id] = str(candidate["stable_id"])
                target_blocks.append(candidate)
                target_ids.add(str(candidate["stable_id"]))
            target_next = target_version + 1
            source_next = source_version + 1
            connection.execute(
                """UPDATE assistant_wiki_pages SET blocks_json=%s,summary=%s,version=%s,updated_at=%s
                WHERE assistant_wiki_pages.workspace_id=%s AND id=%s AND version=%s""",
                (
                    Jsonb(target_blocks),
                    "已合并相关主题；不同说法请按各块条件和来源查看。",
                    target_next,
                    now,
                    self.workspace_id,
                    target_page_id,
                    target_version,
                ),
            )
            for item in source_before["sources"]:
                if str(item["block_id"]) in mapped_ids:
                    connection.execute(
                        """INSERT INTO assistant_wiki_dependencies(workspace_id,
                            page_id,block_id,source_revision,video_id,dependency_kind,created_at
                        ) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                        (
                            self.workspace_id,
                            target_page_id,
                            mapped_ids[str(item["block_id"])],
                            item["source_revision"],
                            item["video_id"],
                            item["dependency_kind"],
                            now,
                        ),
                    )
            for item in source_before["personal"]:
                if str(item["block_id"]) in mapped_ids:
                    connection.execute(
                        """INSERT INTO assistant_wiki_personal_dependencies(workspace_id,
                            page_id,block_id,memory_id,memory_version,source_message_id,created_at
                        ) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                        (
                            self.workspace_id,
                            target_page_id,
                            mapped_ids[str(item["block_id"])],
                            item["memory_id"],
                            item["memory_version"],
                            item["source_message_id"],
                            now,
                        ),
                    )
            for item in source_before["materials"]:
                connection.execute(
                    """INSERT INTO assistant_wiki_materials(workspace_id,
                        page_id,video_id,source_revision,relation,status,created_at,updated_at
                    ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                    (
                        self.workspace_id,
                        target_page_id,
                        item["video_id"],
                        item["source_revision"],
                        item["relation"],
                        item["status"],
                        now,
                        now,
                    ),
                )
            connection.execute(
                "UPDATE assistant_wiki_pages SET status='merged',version=%s,updated_at=%s WHERE assistant_wiki_pages.workspace_id=%s AND id=%s AND version=%s",
                (
                    source_next,
                    now,
                    self.workspace_id,
                    source_page_id,
                    source_version,
                ),
            )
            connection.execute(
                """INSERT INTO assistant_wiki_redirects(workspace_id,old_page_id,target_page_id,space_id,created_at)
                VALUES(%s,%s,%s,%s,%s)""",
                (
                    self.workspace_id,
                    source_page_id,
                    target_page_id,
                    space_id,
                    now,
                ),
            )
            connection.execute(
                "DELETE FROM wiki_windows WHERE workspace_id=%s AND page_id=%s",
                (self.workspace_id, source_page_id),
            )
            target_after = self._operation_state(connection, target_page_id, conn=conn)[
                "page"
            ]
            source_after = self._operation_state(connection, source_page_id, conn=conn)[
                "page"
            ]
            for page_id, version, before_page, after_page in (
                (target_page_id, target_next, target, target_after),
                (source_page_id, source_next, source, source_after),
            ):
                self._record_notification_change(
                    connection,
                    """INSERT INTO assistant_wiki_changes(workspace_id,
                        page_id,version,operation,before_json,after_json,summary,actor,created_at
                    ) VALUES(%s,%s,%s,'merged',%s,%s,%s,'user',%s)""",
                    (
                        self.workspace_id,
                        page_id,
                        version,
                        Jsonb(before_page),
                        Jsonb(after_page),
                        f"合并主题 {source['title']} → {target['title']}",
                        now,
                    ),
                    cause={"operation_key": operation_key},
                    proposal=_notification_proposal,
                )
            self._save_operation_state(
                connection, target_page_id, target_next, target_before, conn=conn
            )
            self._save_operation_state(
                connection, source_page_id, source_next, source_before, conn=conn
            )
            result = {
                "status": "merged",
                "page_id": target_page_id,
                "version": target_next,
                "redirected_page_id": source_page_id,
            }
            connection.execute(
                """INSERT INTO assistant_mutation_receipts(workspace_id,
                    operation_key,principal_id,operation,result_json,created_at
                ) VALUES(%s,%s,%s,'wiki_merge',%s,%s)""",
                (
                    self.workspace_id,
                    operation_key,
                    self.principal_id,
                    Jsonb(result),
                    now,
                ),
            )
        return result

    def decide_proposal(
        self,
        proposal_id: str,
        *,
        accept: bool,
        operation_key: str,
        space_id: int | None = None,
        conn=None,
        prepared_sources=None,
        expected_content_version: int | None = None,
        expected_target_version: int | None = None,
    ) -> dict[str, Any]:
        with self.db.connect(conn, read_only=True) as c:
            original = self._source_proposal(c, proposal_id, space_id=space_id)
        if original["kind"] == "source_patch":
            return self._decide_source_patch(
                original,
                accept=accept,
                operation_key=operation_key,
                expected_content_version=expected_content_version,
                expected_target_version=expected_target_version,
                conn=conn,
            )
        if prepared_sources is None:
            prepared_sources = (
                self._prepare_sources_for_write(space_id=space_id)
                if conn is None
                else {}
            )
        stale = False
        with self._transaction(conn, operation_key=operation_key) as connection:
            row = connection.execute(
                "SELECT * FROM assistant_wiki_proposals WHERE assistant_wiki_proposals.workspace_id=%s AND id=%s AND principal_id=%s",
                (
                    self.workspace_id,
                    proposal_id,
                    self.principal_id,
                ),
            ).fetchone()
            if row is None:
                raise KeyError(proposal_id)
            proposal = dict(row)
            if space_id is not None and int(proposal["space_id"]) != space_id:
                raise KeyError(proposal_id)
            receipt = connection.execute(
                "SELECT result_json FROM assistant_mutation_receipts WHERE assistant_mutation_receipts.workspace_id=%s AND operation_key=%s AND principal_id=%s",
                (
                    self.workspace_id,
                    operation_key,
                    self.principal_id,
                ),
            ).fetchone()
            if receipt is not None:
                result = receipt["result_json"]
                if result.get("proposal_id") != proposal_id:
                    raise AssistantConflict("operation_key_conflict")
                return result
            merge_key = f"wiki_proposal_merge:{proposal_id}"
            if proposal["status"] != "pending":
                merged = (
                    connection.execute(
                        "SELECT result_json FROM assistant_mutation_receipts WHERE assistant_mutation_receipts.workspace_id=%s AND operation_key=%s AND principal_id=%s",
                        (
                            self.workspace_id,
                            merge_key,
                            self.principal_id,
                        ),
                    ).fetchone()
                    if proposal["status"] == "accepted"
                    else None
                )
                return {
                    **((merged["result_json"]) if merged else {}),
                    "status": proposal["status"],
                    "proposal_id": proposal_id,
                }
            if not any(
                item["id"] == proposal_id
                for item in self.list_proposals(
                    space_id=int(proposal["space_id"]),
                    conn=connection,
                    prepared_sources=prepared_sources,
                )
            ):
                connection.execute(
                    "UPDATE assistant_wiki_proposals SET status='stale',updated_at=%s WHERE assistant_wiki_proposals.workspace_id=%s AND id=%s",
                    (
                        utc_now(),
                        self.workspace_id,
                        proposal_id,
                    ),
                )
                stale = True
                result = {"status": "stale", "proposal_id": proposal_id}
            elif not accept:
                connection.execute(
                    "UPDATE assistant_wiki_proposals SET status='rejected',updated_at=%s WHERE assistant_wiki_proposals.workspace_id=%s AND id=%s AND status='pending'",
                    (
                        utc_now(),
                        self.workspace_id,
                        proposal_id,
                    ),
                )
                result = {"status": "rejected", "proposal_id": proposal_id}
            else:
                merged = self.merge_pages(
                    str(proposal["source_page_id"]),
                    str(proposal["target_page_id"]),
                    space_id=int(proposal["space_id"]),
                    source_version=int(proposal["source_version"]),
                    target_version=int(proposal["target_version"]),
                    operation_key=merge_key,
                    accept_conflict=True,
                    _notification_proposal=proposal,
                    _connection=connection,
                    conn=connection,
                    prepared_sources=prepared_sources,
                )
                changed = connection.execute(
                    "UPDATE assistant_wiki_proposals SET status='accepted',updated_at=%s WHERE assistant_wiki_proposals.workspace_id=%s AND id=%s AND status='pending'",
                    (
                        utc_now(),
                        self.workspace_id,
                        proposal_id,
                    ),
                )
                if changed.rowcount != 1:
                    raise AssistantConflict("wiki_proposal_stale")
                result = {**merged, "status": "accepted", "proposal_id": proposal_id}
            identity = self._notify_proposal(
                connection, {**proposal, "updated_at": utc_now()}
            )
            connection.execute(
                "UPDATE assistant_notifications SET activity_at=%s WHERE workspace_id=%s AND principal_id=%s AND id=%s",
                (utc_now(), self.workspace_id, self.principal_id, identity),
            )
            if not stale:
                connection.execute(
                    """INSERT INTO assistant_mutation_receipts(workspace_id,
                        operation_key,principal_id,operation,result_json,created_at
                    ) VALUES(%s,%s,%s,'wiki_proposal_decision',%s,%s)""",
                    (
                        self.workspace_id,
                        operation_key,
                        self.principal_id,
                        Jsonb(result),
                        utc_now(),
                    ),
                )
        if stale:
            raise AssistantConflict("wiki_proposal_stale")
        return result

    def list_proposals(
        self, *, space_id: int, conn=None, prepared_sources=None
    ) -> list[dict[str, Any]]:
        if prepared_sources is None:
            prepared_sources = {}
        self.store.get_space(space_id, conn=conn)
        with self.db.connect(conn) as connection:
            rows = connection.execute(
                """SELECT * FROM assistant_wiki_proposals
                WHERE assistant_wiki_proposals.workspace_id=%s AND principal_id=%s AND space_id=%s AND status='pending'
                ORDER BY created_at DESC""",
                (
                    self.workspace_id,
                    self.principal_id,
                    space_id,
                ),
            ).fetchall()
        values = []
        for row in rows:
            item = dict(row)
            if item["kind"] == "source_patch":
                with self.db.connect(conn, read_only=True) as c:
                    values.append(self._source_patch_view(c, item))
                continue
            if (
                item["kind"] != "merge"
                or not item["source_page_id"]
                or not item["source_version"]
            ):
                continue
            with self.db.connect(conn, read_only=True) as c:
                for pid in (item["source_page_id"], item["target_page_id"]):
                    evidence = self._notification_cache(c, pid)
                    prepared_sources.setdefault("@current", {}).update(
                        evidence.pop("@current", {})
                    )
                    prepared_sources.update(evidence)
            try:
                source = self.get_page(
                    str(item["source_page_id"]),
                    space_id=space_id,
                    conn=conn,
                    prepared_sources=prepared_sources,
                )
                target = self.get_page(
                    str(item["target_page_id"]),
                    space_id=space_id,
                    conn=conn,
                    prepared_sources=prepared_sources,
                )
            except KeyError:
                continue
            if int(source["version"]) != int(item["source_version"]) or int(
                target["version"]
            ) != int(item["target_version"]):
                continue
            ids = set((item["payload_json"]).get("conflict_block_ids", []))
            differences = []
            for block in source["blocks"]:
                if block["stable_id"] not in ids:
                    continue
                counterpart = next(
                    (
                        candidate
                        for candidate in target["blocks"]
                        if candidate.get("manual_lock")
                        and str(candidate["heading"]).strip().casefold()
                        == str(block["heading"]).strip().casefold()
                    ),
                    None,
                )
                if counterpart is not None:
                    differences.append(
                        {
                            "heading": block["heading"],
                            "source_text": block["markdown"],
                            "target_text": counterpart["markdown"],
                        }
                    )
            if not differences:
                continue
            values.append(
                {
                    "id": item["id"],
                    "kind": "merge",
                    "source_page_id": source["id"],
                    "source_title": source["title"],
                    "target_page_id": target["id"],
                    "target_title": target["title"],
                    "differences": differences,
                }
            )
        return values

    def revert(
        self,
        page_id: str,
        *,
        target_version: int,
        expected_version: int,
        operation_key: str,
        conn=None,
        _notification_id=None,
        prepared_sources=None,
    ) -> dict[str, Any]:
        if prepared_sources is None:
            prepared_sources = (
                self._prepare_sources_for_write(page_id=page_id) if conn is None else {}
            )
        now = utc_now()
        with self._transaction(
            conn, operation_key=operation_key, page_ids=[page_id]
        ) as connection:
            receipt = connection.execute(
                "SELECT result_json FROM assistant_mutation_receipts WHERE assistant_mutation_receipts.workspace_id=%s AND operation_key=%s AND principal_id=%s",
                (
                    self.workspace_id,
                    operation_key,
                    self.principal_id,
                ),
            ).fetchone()
            if receipt is not None:
                return self._visible_page(
                    (receipt["result_json"]),
                    conn=connection,
                    snapshot_cache=prepared_sources,
                )
            row = connection.execute(
                "SELECT * FROM assistant_wiki_pages WHERE assistant_wiki_pages.workspace_id=%s AND id=%s AND principal_id=%s",
                (
                    self.workspace_id,
                    page_id,
                    self.principal_id,
                ),
            ).fetchone()
            if row is None:
                raise KeyError(page_id)
            before = self._decode_page(dict(row))
            self._assert_lifecycle(before)
            before_state = self._operation_state(connection, page_id, conn=connection)
            if int(before["version"]) != expected_version:
                raise AssistantConflict("wiki_version_conflict")
            if target_version >= expected_version:
                raise ValueError("invalid_revert_version")
            state_row = connection.execute(
                "SELECT after_json FROM assistant_wiki_operation_states WHERE assistant_wiki_operation_states.workspace_id=%s AND page_id=%s AND version=%s",
                (
                    self.workspace_id,
                    page_id,
                    target_version,
                ),
            ).fetchone()
            if state_row is not None:
                target_state = state_row["after_json"]
            else:
                state_row = connection.execute(
                    "SELECT before_json FROM assistant_wiki_operation_states WHERE assistant_wiki_operation_states.workspace_id=%s AND page_id=%s AND version=%s",
                    (
                        self.workspace_id,
                        page_id,
                        target_version + 1,
                    ),
                ).fetchone()
                if state_row is None or not state_row["before_json"]:
                    raise AssistantConflict("revert_dependency_snapshot_unavailable")
                target_state = state_row["before_json"]
            later_changes = connection.execute(
                """SELECT operation,before_json,after_json FROM assistant_wiki_changes
                WHERE assistant_wiki_changes.workspace_id=%s AND page_id=%s AND version>%s ORDER BY version""",
                (
                    self.workspace_id,
                    page_id,
                    target_version + 1,
                ),
            ).fetchall()
            if any(
                str(item["operation"])
                not in {
                    "block_edited",
                    "personal_note_added",
                    "delete_block",
                    "restore_block",
                }
                for item in later_changes
            ):
                raise AssistantConflict("revert_later_source_change_conflict")
            independent_ids: set[str] = set()
            for item in later_changes:
                old = {
                    str(block["stable_id"]): block
                    for block in (item["before_json"] or {}).get("blocks", [])
                }
                new = {
                    str(block["stable_id"]): block
                    for block in (item["after_json"]).get("blocks", [])
                }
                independent_ids.update(
                    block_id
                    for block_id, block in new.items()
                    if block.get("manual_lock") and block != old.get(block_id)
                )
            target = target_state["page"]
            desired_sources = target_state["sources"]
            desired_personal = target_state["personal"]
            current_blocks = {
                str(block["stable_id"]): block for block in before["blocks"]
            }
            desired_blocks = {
                str(block["stable_id"]): block for block in target["blocks"]
            }
            restored_blocks = []
            for block_id, block in desired_blocks.items():
                restored_blocks.append(
                    current_blocks[block_id]
                    if block_id in independent_ids and block_id in current_blocks
                    else block
                )
            for block_id in sorted(independent_ids - desired_blocks.keys()):
                if block_id in current_blocks:
                    restored_blocks.append(current_blocks[block_id])
            lifecycle_ids = {
                str(b["stable_id"])
                for b in before["blocks"]
                if int(b.get("lifecycle_version", 0)) > target_version
            }
            independent_ids.update(lifecycle_ids)
            restored_blocks = [
                b for b in restored_blocks if str(b["stable_id"]) not in lifecycle_ids
            ]
            restored_blocks.extend(
                b for b in before["blocks"] if str(b["stable_id"]) in lifecycle_ids
            )
            space = self.store.get_space(int(before["space_id"]), conn=connection)
            visible_ids = set(
                self.sources.visible_video_ids(self._scope(space), conn=conn)
            )
            valid_source_revisions = {
                str(item["source_revision"])
                for item in connection.execute(
                    """SELECT h.current_revision AS source_revision,h.video_id
                    FROM assistant_source_heads h WHERE h.workspace_id=%s AND h.principal_id=%s""",
                    (
                        self.workspace_id,
                        self.principal_id,
                    ),
                ).fetchall()
                if int(item["video_id"]) in visible_ids
            }
            current_source_rows = [
                item
                for item in before_state["sources"]
                if str(item["block_id"]) in independent_ids
            ]
            source_rows = [
                item
                for item in desired_sources
                if str(item["block_id"]) not in independent_ids
            ] + current_source_rows
            current_personal_rows = [
                item
                for item in before_state["personal"]
                if str(item["block_id"]) in independent_ids
            ]
            personal_rows = [
                item
                for item in desired_personal
                if str(item["block_id"]) not in independent_ids
            ] + current_personal_rows
            kept_blocks = []
            for block in restored_blocks:
                block_id = str(block["stable_id"])
                if block.get("deleted"):
                    kept_blocks.append(block)
                    continue
                refs = {
                    str(item["source_revision"])
                    for item in source_rows
                    if str(item["block_id"]) == block_id
                }
                if block.get("source_refs") and (
                    not refs or not refs.issubset(valid_source_revisions)
                ):
                    continue
                deps = [
                    item for item in personal_rows if str(item["block_id"]) == block_id
                ]
                if deps and not all(
                    self._personal_dependency_current(
                        connection,
                        space_id=int(before["space_id"]),
                        memory_id=str(item["memory_id"]),
                        memory_version=int(item["memory_version"]),
                        source_message_id=item["source_message_id"],
                        conn=connection,
                    )
                    for item in deps
                ):
                    continue
                kept_blocks.append(block)
            kept_ids = {str(block["stable_id"]) for block in kept_blocks}
            source_rows = [
                item for item in source_rows if str(item["block_id"]) in kept_ids
            ]
            personal_rows = [
                item for item in personal_rows if str(item["block_id"]) in kept_ids
            ]
            version = expected_version + 1
            updated = connection.execute(
                """
                UPDATE assistant_wiki_pages SET title=%s, normalized_title=%s, page_type=%s,
                    summary=%s, blocks_json=%s, version=%s, updated_at=%s
                WHERE assistant_wiki_pages.workspace_id=%s AND id=%s AND version=%s
                """,
                (
                    target["title"],
                    self._normalize_title(target["title"]),
                    target["page_type"],
                    self._pending_guide(),
                    Jsonb(kept_blocks),
                    version,
                    now,
                    self.workspace_id,
                    page_id,
                    expected_version,
                ),
            )
            if updated.rowcount != 1:
                raise AssistantConflict("wiki_version_conflict")
            connection.execute(
                "DELETE FROM assistant_wiki_dependencies WHERE assistant_wiki_dependencies.workspace_id=%s AND page_id=%s",
                (
                    self.workspace_id,
                    page_id,
                ),
            )
            for item in source_rows:
                connection.execute(
                    """INSERT INTO assistant_wiki_dependencies(workspace_id,
                        page_id,block_id,source_revision,video_id,dependency_kind,created_at
                    ) VALUES(%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        self.workspace_id,
                        page_id,
                        item["block_id"],
                        item["source_revision"],
                        item["video_id"],
                        item["dependency_kind"],
                        now,
                    ),
                )
            connection.execute(
                "DELETE FROM assistant_wiki_personal_dependencies WHERE assistant_wiki_personal_dependencies.workspace_id=%s AND page_id=%s",
                (
                    self.workspace_id,
                    page_id,
                ),
            )
            for item in personal_rows:
                connection.execute(
                    """INSERT INTO assistant_wiki_personal_dependencies(workspace_id,
                        page_id,block_id,memory_id,memory_version,source_message_id,created_at
                    ) VALUES(%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        self.workspace_id,
                        page_id,
                        item["block_id"],
                        item["memory_id"],
                        item["memory_version"],
                        item["source_message_id"],
                        now,
                    ),
                )
            connection.execute(
                "DELETE FROM assistant_wiki_materials WHERE assistant_wiki_materials.workspace_id=%s AND page_id=%s",
                (
                    self.workspace_id,
                    page_id,
                ),
            )
            for item in target_state["materials"]:
                if str(item["source_revision"]) not in valid_source_revisions:
                    continue
                connection.execute(
                    """INSERT INTO assistant_wiki_materials(workspace_id,
                        page_id,video_id,source_revision,relation,status,created_at,updated_at
                    ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        self.workspace_id,
                        page_id,
                        item["video_id"],
                        item["source_revision"],
                        item["relation"],
                        item["status"],
                        now,
                        now,
                    ),
                )
            old_redirects = {
                str(item["old_page_id"]) for item in target_state["redirects"]
            }
            current_redirects = {
                str(item["old_page_id"]) for item in before_state["redirects"]
            }
            for old_page_id in current_redirects - old_redirects:
                source_row = connection.execute(
                    "SELECT * FROM assistant_wiki_pages WHERE assistant_wiki_pages.workspace_id=%s AND id=%s AND status='merged'",
                    (
                        self.workspace_id,
                        old_page_id,
                    ),
                ).fetchone()
                if source_row is None:
                    raise AssistantConflict("revert_merge_source_changed")
                source_before = self._operation_state(
                    connection, old_page_id, conn=connection
                )
                source_version = int(source_row["version"])
                last_source_change = connection.execute(
                    "SELECT operation FROM assistant_wiki_changes WHERE assistant_wiki_changes.workspace_id=%s AND page_id=%s AND version=%s",
                    (
                        self.workspace_id,
                        old_page_id,
                        source_version,
                    ),
                ).fetchone()
                if (
                    last_source_change is None
                    or str(last_source_change["operation"]) != "merged"
                ):
                    raise AssistantConflict("revert_merge_source_changed")
                # A later delete on the merged target also applies when restoring its source.
                # Match identities or the exact pre-delete text, never semantic similarity.
                source_blocks = self._decode_page(dict(source_row))["blocks"]
                clean = lambda text: " ".join(str(text or "").split())
                for block in source_blocks:
                    for tomb in self._deleted_blocks(before):
                        if block["stable_id"] in {
                            tomb["stable_id"],
                            tomb.get("deleted_stable_id"),
                        } or (clean(block["heading"]), clean(block["markdown"])) == (
                            clean(tomb["heading"]),
                            clean(tomb["markdown"]),
                        ):
                            block.update(
                                deleted=True,
                                manual_lock=True,
                                deletion_released=False,
                                lock_before_delete=bool(block.get("manual_lock")),
                                lifecycle_version=source_version + 1,
                            )
                connection.execute(
                    "DELETE FROM assistant_wiki_redirects WHERE assistant_wiki_redirects.workspace_id=%s AND old_page_id=%s",
                    (
                        self.workspace_id,
                        old_page_id,
                    ),
                )
                connection.execute(
                    "UPDATE assistant_wiki_pages SET status='active',blocks_json=%s,summary=%s,version=%s,updated_at=%s WHERE assistant_wiki_pages.workspace_id=%s AND id=%s",
                    (
                        Jsonb(source_blocks),
                        self._pending_guide(),
                        source_version + 1,
                        now,
                        self.workspace_id,
                        old_page_id,
                    ),
                )
                source_after = self._operation_state(
                    connection, old_page_id, conn=connection
                )["page"]
                self._record_notification_change(
                    connection,
                    """INSERT INTO assistant_wiki_changes(workspace_id,
                        page_id,version,operation,before_json,after_json,summary,actor,created_at
                    ) VALUES(%s,%s,%s,'merge_undone',%s,%s,%s,'user',%s)""",
                    (
                        self.workspace_id,
                        old_page_id,
                        source_version + 1,
                        Jsonb(source_before["page"]),
                        Jsonb(source_after),
                        "撤销合并，恢复原主题入口",
                        now,
                    ),
                    cause={"operation_key": operation_key},
                    undo_id=_notification_id,
                )
                self._save_operation_state(
                    connection,
                    old_page_id,
                    source_version + 1,
                    source_before,
                    conn=connection,
                )
            after = self._decode_page(
                dict(
                    connection.execute(
                        "SELECT * FROM assistant_wiki_pages WHERE assistant_wiki_pages.workspace_id=%s AND id=%s",
                        (
                            self.workspace_id,
                            page_id,
                        ),
                    ).fetchone()
                )
            )
            self._record_notification_change(
                connection,
                """
                INSERT INTO assistant_wiki_changes(workspace_id,
                    page_id, version, operation, before_json, after_json, summary, actor, created_at
                ) VALUES(%s,%s, %s, 'reverted', %s, %s, %s, 'user', %s)
                """,
                (
                    self.workspace_id,
                    page_id,
                    version,
                    Jsonb(before),
                    Jsonb(after),
                    f"恢复到版本 {target_version}",
                    now,
                ),
                cause={"operation_key": operation_key},
                undo_id=_notification_id,
            )
            self._save_operation_state(
                connection, page_id, version, before_state, conn=connection
            )
            connection.execute(
                """
                INSERT INTO assistant_mutation_receipts(workspace_id,
                    operation_key, principal_id, operation, result_json, created_at
                ) VALUES(%s,%s, %s, 'wiki_revert', %s, %s)
                """,
                (
                    self.workspace_id,
                    operation_key,
                    self.principal_id,
                    Jsonb(after),
                    now,
                ),
            )
        return self._visible_page(after, conn=conn, snapshot_cache=prepared_sources)

    def get_source_card(self, revision: str, *, conn=None) -> dict[str, Any] | None:
        with self.db.connect(conn) as connection:
            row = connection.execute(
                "SELECT card_json FROM assistant_source_cards WHERE assistant_source_cards.workspace_id=%s AND revision=%s",
                (
                    self.workspace_id,
                    revision,
                ),
            ).fetchone()
        return (row["card_json"]) if row else None

    def _commit_source_card(
        self,
        captured: CapturedSource,
        *,
        input_hash: str,
        card: dict[str, Any],
        payload: dict | None = None,
        conn=None,
        job=None,
    ) -> None:
        now = utc_now()
        video_id = int(captured.snapshot["metadata"]["id"])
        with self._transaction(
            conn,
            job_claim=(job["id"], job["lease_owner"], job["lease_epoch"])
            if job
            else None,
        ) as connection:
            self._require_publish_allowed(connection=connection, conn=connection)
            if payload is not None:
                self._require_maintenance_authorized(
                    payload, connection=connection, conn=connection
                )
            head = connection.execute(
                "SELECT current_revision FROM assistant_source_heads WHERE assistant_source_heads.workspace_id=%s AND video_id=%s AND principal_id=%s",
                (
                    self.workspace_id,
                    video_id,
                    self.principal_id,
                ),
            ).fetchone()
            if head is None or str(head["current_revision"]) != captured.revision:
                raise AssistantConflict("source_revision_changed")
            connection.execute(
                """
                INSERT INTO assistant_source_cards(workspace_id,
                    revision, video_id, input_hash, card_json, coverage,
                    extraction_version, created_at, updated_at
                ) VALUES(%s,%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(revision) DO UPDATE SET
                    input_hash=excluded.input_hash, card_json=excluded.card_json,
                    coverage=excluded.coverage, extraction_version=excluded.extraction_version,
                    updated_at=excluded.updated_at
                WHERE assistant_source_cards.extraction_version<>excluded.extraction_version
                """,
                (
                    self.workspace_id,
                    *(
                        self.workspace_id,
                        captured.revision,
                        video_id,
                        input_hash,
                        Jsonb(card),
                        card["coverage"],
                        self.EXTRACTION_VERSION,
                        now,
                        now,
                    )[1:],
                ),
            )

    def _enqueue_integrations(
        self,
        video_id: int,
        revision: str,
        *,
        batch_id: str | None = None,
        task_topic: str | None = None,
        request_key: str | None = None,
        source_message_id: str | None = None,
        task_subset: list[int] | None = None,
        expected_scope_version: int | None = None,
        conn=None,
    ) -> list[str]:
        jobs: list[str] = []
        if request_key:
            spaces = [
                self.store.get_space(int(str(request_key).split(":", 1)[0]), conn=conn)
            ]
        elif batch_id:
            with self.db.connect(conn) as connection:
                row = connection.execute(
                    "SELECT space_id FROM assistant_maintenance_batches WHERE assistant_maintenance_batches.workspace_id=%s AND id=%s",
                    (
                        self.workspace_id,
                        batch_id,
                    ),
                ).fetchone()
            spaces = (
                [self.store.get_space(int(row["space_id"]), conn=conn)] if row else []
            )
        else:
            spaces = [
                space
                for space in self._spaces_for_video(video_id, conn=conn)
                if space.get("maintenance_mode") == "automatic"
            ]
        for space in spaces:
            if expected_scope_version is not None and int(
                space["scope_version"]
            ) != int(expected_scope_version):
                continue
            if video_id not in self.sources.visible_video_ids(
                self._scope(space), conn=conn
            ):
                continue
            card = self.get_source_card(revision, conn=conn)
            topics = (
                [str(task_topic)]
                if task_topic
                else [
                    str(value)
                    for value in (card or {}).get("topics", [])[:5]
                    if str(value).strip()
                ]
            )
            if not topics:
                topics = [str((card or {}).get("title") or "未命名材料")]
            if not task_topic:
                with self.db.connect(conn) as connection:
                    linked_topics = [
                        str(row["title"])
                        for row in connection.execute(
                            """SELECT p.title FROM assistant_wiki_materials m
                        JOIN assistant_wiki_pages p ON p.id=m.page_id
                        WHERE m.workspace_id=%s AND m.video_id=%s AND p.space_id=%s AND p.status='active'""",
                            (
                                self.workspace_id,
                                video_id,
                                int(space["id"]),
                            ),
                        ).fetchall()
                    ]
                primary = topics[0]
                candidates = [
                    topic
                    for topic in topics[1:]
                    if self._find_page(int(space["id"]), topic, conn=conn) is not None
                    or self._find_related_page(
                        int(space["id"]), {"topics": [topic]}, conn=conn
                    )
                    is not None
                ]
                topics = (
                    [primary, *candidates, *linked_topics]
                    if batch_id
                    else [
                        topic
                        for topic in topics
                        if self._find_page(int(space["id"]), topic, conn=conn)
                        is not None
                        or self._find_related_page(
                            int(space["id"]), {"topics": [topic]}, conn=conn
                        )
                        is not None
                    ]
                    + linked_topics
                )
            review_target = {}
            if request_key:
                with self.db.connect(conn) as c:
                    root = c.execute(
                        "SELECT payload_json FROM assistant_jobs WHERE workspace_id=%s AND principal_id=%s AND kind='source_reconcile' AND dedupe_key=%s",
                        (
                            self.workspace_id,
                            self.principal_id,
                            f"topic_request:{request_key}:{video_id}",
                        ),
                    ).fetchone()
                    review_id = (root["payload_json"] if root else {}).get(
                        "review_proposal_id"
                    )
                    if review_id:
                        original = self._source_proposal(
                            c, review_id, space_id=space["id"]
                        )
                        review_target = {
                            "review_proposal_id": review_id,
                            "repair_page_id": original["target_page_id"],
                        }
            for topic in dict.fromkeys(topics):
                with self.db.connect(conn) as connection:
                    jobs.append(
                        self.store.enqueue_job(
                            connection,
                            kind="wiki_integrate",
                            dedupe_key=(
                                f"wiki_integrate:{space['id']}:{revision}:{self.COMPILER_VERSION}:"
                                f"{hashlib.sha256(topic.encode('utf-8')).hexdigest()[:16]}"
                                + (f":batch:{batch_id}" if batch_id else "")
                                + (f":task:{request_key}" if request_key else "")
                            ),
                            payload={
                                "space_id": space["id"],
                                "scope_version": space["scope_version"],
                                "video_id": video_id,
                                "revision": revision,
                                "compiler_version": self.COMPILER_VERSION,
                                "topic": topic,
                                **review_target,
                                **({"task_subset": task_subset} if task_subset else {}),
                                **(
                                    {"task_topic": topic, "request_key": request_key}
                                    if request_key
                                    else {}
                                ),
                                **(
                                    {"source_message_id": source_message_id}
                                    if source_message_id
                                    else {}
                                ),
                                **(
                                    {"maintenance_batch_id": batch_id}
                                    if batch_id
                                    else {}
                                ),
                            },
                        )
                    )
        return jobs

    def _spaces_for_video(self, video_id: int, *, conn=None) -> list[dict[str, Any]]:
        values = []
        for space in self.store.list_spaces(conn=conn):
            if video_id in self.sources.visible_video_ids(
                self._scope(space), conn=conn
            ):
                values.append(space)
        return values

    @staticmethod
    def _pending_guide() -> str:
        return "导读未随本次修改重写；请查看下方各条内容、条件及来源。"

    def _visible_page(
        self, page: dict[str, Any], *, conn=None, snapshot_cache=None
    ) -> dict[str, Any]:
        space = self.store.get_space(int(page["space_id"]), conn=conn)
        visible_video_ids = set(
            self.sources.visible_video_ids(self._scope(space), conn=conn)
        )
        with self.db.connect(conn) as connection:
            rows = connection.execute(
                """
                SELECT d.block_id, d.video_id, d.source_revision, d.dependency_kind, h.current_revision,
                       c.card_json, v.video_url
                FROM assistant_wiki_dependencies d
                LEFT JOIN assistant_source_cards c ON c.revision=d.source_revision
                LEFT JOIN videos v ON v.id=d.video_id
                LEFT JOIN assistant_source_heads h ON h.video_id=d.video_id
                    AND h.principal_id=%s
                WHERE d.workspace_id=%s AND d.page_id=%s
                """,
                (
                    self.principal_id,
                    self.workspace_id,
                    page["id"],
                ),
            ).fetchall()
            personal_rows = connection.execute(
                """SELECT block_id,memory_id,memory_version,source_message_id
                FROM assistant_wiki_personal_dependencies WHERE assistant_wiki_personal_dependencies.workspace_id=%s AND page_id=%s""",
                (
                    self.workspace_id,
                    page["id"],
                ),
            ).fetchall()
            valid_personal = {
                str(item["block_id"]): self._personal_dependency_current(
                    connection,
                    space_id=int(page["space_id"]),
                    memory_id=str(item["memory_id"]),
                    memory_version=int(item["memory_version"]),
                    source_message_id=item["source_message_id"],
                    conn=connection,
                )
                for item in personal_rows
            }
            material_rows = connection.execute(
                """SELECT m.video_id,m.source_revision,m.relation,m.status,
                          h.current_revision,c.card_json,v.video_url
                FROM assistant_wiki_materials m
                LEFT JOIN assistant_source_heads h ON h.video_id=m.video_id AND h.principal_id=%s
                LEFT JOIN assistant_source_cards c ON c.revision=m.source_revision
                LEFT JOIN videos v ON v.id=m.video_id
                WHERE m.workspace_id=%s AND m.page_id=%s ORDER BY m.created_at,m.video_id""",
                (
                    self.principal_id,
                    self.workspace_id,
                    page["id"],
                ),
            ).fetchall()
        if snapshot_cache is not None:
            for row in rows:
                prepared_current = snapshot_cache.get("@current", {}).get(
                    row["video_id"]
                )
                if prepared_current:
                    row["current_revision"] = prepared_current["revision"]
        dependencies: dict[str, set[int]] = {}
        current_dependencies: dict[str, set[int]] = {}
        source_details: dict[str, list[dict[str, Any]]] = {}
        snapshot_cache = {} if snapshot_cache is None else snapshot_cache
        for row in rows:
            dependencies.setdefault(str(row["block_id"]), set()).add(
                int(row["video_id"])
            )
            if int(
                row["video_id"]
            ) in visible_video_ids and self._source_dependency_current(
                video_id=int(row["video_id"]),
                old_revision=str(row["source_revision"]),
                current_revision=str(row["current_revision"] or ""),
                dependency_kind=str(row["dependency_kind"] or "source"),
                cache=snapshot_cache,
                conn=conn,
            ):
                current_dependencies.setdefault(str(row["block_id"]), set()).add(
                    int(row["video_id"])
                )
            if int(row["video_id"]) in current_dependencies.get(
                str(row["block_id"]), set()
            ):
                if row["card_json"]:
                    card = row["card_json"]
                else:
                    revision = str(row["source_revision"])
                    if revision not in snapshot_cache:
                        if conn is not None:
                            raise AssistantConflict("wiki_snapshot_prepare_stale")
                        snapshot_cache[revision] = self.sources._capture_or_load(
                            int(row["video_id"]), revision
                        ).snapshot
                    snapshot = snapshot_cache[revision]
                    card = {
                        **snapshot.get("metadata", {}),
                        "memberships": snapshot.get("memberships", []),
                        "coverage": snapshot.get("coverage"),
                        "material_kind": "未生成来源卡",
                    }
                source_details.setdefault(str(row["block_id"]), []).append(
                    {
                        "source_ref": f"video:{int(row['video_id'])}:{row['source_revision']}",
                        "title": card.get("title") or "未命名材料",
                        "uploader": card.get("uploader") or "",
                        "published_at": card.get("published_at"),
                        "collected_at": max(
                            (
                                item.get("favorite_time")
                                for item in card.get("memberships", [])
                                if item.get("favorite_time") is not None
                            ),
                            default=None,
                        ),
                        "coverage": card.get("coverage") or "metadata_only",
                        "url": str(row["video_url"] or ""),
                        "material_view": card.get("material_kind") or "未知",
                    }
                )
        blocks = []
        suppressed_quotes = self._memories().suppressed_source_message_ids(
            space_id=int(page["space_id"]), conn=conn
        )
        for block in page["blocks"]:
            if block.get("user_message_id") in suppressed_quotes:
                continue
            if block.get("deleted"):
                continue
            if block.get("expires_at"):
                try:
                    if datetime.fromisoformat(
                        str(block["expires_at"]).replace("Z", "+00:00")
                    ) <= datetime.fromisoformat(utc_now()):
                        continue
                except ValueError:
                    continue
            if (
                block["stable_id"] in valid_personal
                and not valid_personal[block["stable_id"]]
            ):
                continue
            if block.get("external_sources"):
                with self.db.connect(conn) as connection:
                    message_thread = connection.execute(
                        "SELECT thread_id FROM assistant_messages WHERE assistant_messages.workspace_id=%s AND id=%s",
                        (
                            self.workspace_id,
                            block.get("source_message_id"),
                        ),
                    ).fetchone()
                if message_thread is None:
                    continue
                try:
                    for external in block["external_sources"]:
                        self.store.resolve_run_result(
                            str(external["result_ref"]),
                            current_thread_id=str(message_thread["thread_id"]),
                            current_scope_version=int(space["scope_version"]),
                            conn=conn,
                        )
                except (KeyError, ValueError):
                    continue
            block_dependencies = dependencies.get(block["stable_id"], set())
            if (block.get("source_refs") and not block_dependencies) or (
                block_dependencies
                and current_dependencies.get(block["stable_id"], set())
                != block_dependencies
            ):
                continue
            value = dict(block)
            if not value.get("speaker_verified"):
                value["speaker"] = ""
            if value.get("cited_source") and not self._reference_like(
                str(value["cited_source"])
            ):
                value["cited_source"] = ""
            for field in ("markdown", "heading", "applicability"):
                clean = re.sub(
                    r"coverage=[a-z_]+", "当前可用材料", str(value.get(field) or "")
                )
                value[field] = re.sub(r"material_kind=[a-z_]+", "摘要材料视图", clean)
            value["sources"] = source_details.get(block["stable_id"], [])
            blocks.append(value)
        value = dict(page)
        value["blocks"] = blocks
        value["materials"] = [
            {
                "video_id": int(item["video_id"]),
                "title": str(
                    ((item["card_json"]) if item["card_json"] else {}).get("title")
                    or "材料"
                ),
                "url": str(item["video_url"] or ""),
                "relation": str(item["relation"]),
                "status": str(item["status"]),
            }
            for item in material_rows
            if int(item["video_id"]) in visible_video_ids
            and str(item["source_revision"]) == str(item["current_revision"] or "")
        ]
        value["summary"] = re.sub(
            r"coverage=[a-z_]+", "当前可用材料", str(value.get("summary") or "")
        )
        if any(block.get("deleted") for block in page["blocks"]):
            value["summary"] = self._pending_guide()
        value["availability"] = (
            "full" if len(blocks) == len(page["blocks"]) else "partial"
        )
        current_source_blocks = [
            block
            for block in blocks
            if block.get("source_refs") or block.get("external_sources")
        ]
        visible_block_ids = {str(block["stable_id"]) for block in blocks}
        missing_source = any(
            block.get("source_refs")
            and str(block["stable_id"]) not in visible_block_ids
            for block in page["blocks"]
        )
        if value["availability"] == "partial" or not current_source_blocks:
            if current_source_blocks:
                notice = (
                    "部分来源已失效；以下仅展示当前有效的来源内容和个人笔记。"
                    if missing_source
                    else "部分依赖个人内容已失效；来源内容和独立个人笔记仍可查看。"
                )
                value["summary"] = f"{notice} {value['summary']}"
            elif blocks and any(
                block.get("assessment") == "system_synthesis" for block in blocks
            ):
                value["summary"] = (
                    self._pending_guide()
                    if any(b.get("deleted") for b in page["blocks"])
                    else str(page.get("summary") or "")
                )
            elif blocks:
                value["summary"] = "主题正文暂不可用；以下仅保留独立个人笔记。"
            else:
                value["summary"] = "暂无当前可用的主题正文。"
        return value

    def personal_dependency_refs(
        self, page_id: str, *, space_id: int, conn=None
    ) -> list[str]:
        page = self.get_page(page_id, space_id=space_id, conn=conn)
        visible = {str(block["stable_id"]) for block in page["blocks"]}
        with self.db.connect(conn) as connection:
            rows = connection.execute(
                """SELECT block_id,memory_id,memory_version FROM assistant_wiki_personal_dependencies
                WHERE assistant_wiki_personal_dependencies.workspace_id=%s AND page_id=%s""",
                (
                    self.workspace_id,
                    page_id,
                ),
            ).fetchall()
        return sorted(
            {
                f"memory:{row['memory_id']}:{int(row['memory_version'])}"
                for row in rows
                if str(row["block_id"]) in visible
            }
        )

    def _extract_batch(
        self,
        provider: StructuredProvider,
        *,
        snapshot: dict[str, Any],
        material_kind: str,
        material: str,
        batch_index: int,
        batch_total: int,
        conn=None,
    ) -> dict[str, Any]:
        return provider.generate_json(
            system=(
                "你是拾流 SourceCard 提炼器。只依据给定材料，材料不足就留空；"
                "不得把标题推测成视频内容。已有注释与作者观点分开，注释作者未知时不要说成当前用户判断。"
                "上传者、发言者与被引出处是不同角色；识别引用不等于核对官方原文。返回 JSON 对象。"
            ),
            prompt=(
                "生成 SourceCard：{summary:string,key_points:[{heading,markdown,applicability,assessment,evidence_quote,speaker,cited_source}],"
                "topics:[string],limitations:[string]}。key_points 最多 8 条；assessment 只能是 "
                "source_reported 或 user_annotation。\n"
                + json.dumps(
                    {
                        "title": snapshot["metadata"].get("title"),
                        "uploader": snapshot["metadata"].get("uploader"),
                        "coverage": snapshot["coverage"],
                        "material_kind": material_kind,
                        "batch": {"index": batch_index + 1, "total": batch_total},
                        "material": material,
                    },
                    ensure_ascii=False,
                )
            ),
            max_tokens=2400,
        )

    def _save_card_batch(
        self,
        revision: str,
        *,
        batch_index: int,
        input_hash: str,
        response: dict[str, Any],
        conn=None,
        job=None,
    ) -> None:
        with self._transaction(
            conn,
            job_claim=(job["id"], job["lease_owner"], job["lease_epoch"])
            if job
            else None,
        ) as connection:
            if job is not None and not self._maintenance_authorized(
                job["payload"], connection=connection, conn=connection
            ):
                raise AssistantConflict("wiki_maintenance_not_authorized")
            connection.execute(
                """
                INSERT INTO assistant_source_card_batches(workspace_id,
                    revision, batch_index, input_hash, card_json, created_at
                ) VALUES(%s,%s, %s, %s, %s, %s)
                ON CONFLICT(revision, batch_index) DO UPDATE SET
                    input_hash=excluded.input_hash, card_json=excluded.card_json
                """,
                (
                    self.workspace_id,
                    revision,
                    batch_index,
                    input_hash,
                    Jsonb(response),
                    utc_now(),
                ),
            )

    def _merge_card_batches(self, revision: str, *, conn=None) -> dict[str, Any]:
        with self.db.connect(conn) as connection:
            rows = connection.execute(
                "SELECT card_json FROM assistant_source_card_batches WHERE assistant_source_card_batches.workspace_id=%s AND revision=%s ORDER BY batch_index",
                (
                    self.workspace_id,
                    revision,
                ),
            ).fetchall()
        cards = [(row["card_json"]) for row in rows]
        return {
            "summary": "\n\n".join(
                str(card.get("summary") or "").strip()
                for card in cards
                if str(card.get("summary") or "").strip()
            )[:3000],
            "key_points": [
                point for card in cards for point in (card.get("key_points") or [])
            ][:8],
            "topics": list(
                dict.fromkeys(
                    str(topic).strip()
                    for card in cards
                    for topic in (card.get("topics") or [])
                    if str(topic).strip()
                )
            )[:5],
            "limitations": list(
                dict.fromkeys(
                    str(item).strip()
                    for card in cards
                    for item in (card.get("limitations") or [])
                    if str(item).strip()
                )
            )[:5],
        }

    def _find_page(
        self, space_id: int, title: str, *, conn=None
    ) -> dict[str, Any] | None:
        normalized = self._normalize_title(title)
        with self.db.connect(conn) as connection:
            row = connection.execute(
                """
                SELECT * FROM assistant_wiki_pages
                WHERE assistant_wiki_pages.workspace_id=%s AND principal_id=%s AND space_id=%s AND normalized_title=%s
                """,
                (
                    self.workspace_id,
                    self.principal_id,
                    space_id,
                    normalized,
                ),
            ).fetchone()
        return self._decode_page(dict(row)) if row else None

    def _find_related_page(
        self, space_id: int, card: dict[str, Any], *, conn=None
    ) -> dict[str, Any] | None:
        topics = [
            str(value).strip() for value in card.get("topics", []) if str(value).strip()
        ]
        if not topics:
            return None
        with self.db.connect(conn) as connection:
            rows = connection.execute(
                """
                SELECT * FROM assistant_wiki_pages
                WHERE assistant_wiki_pages.workspace_id=%s AND principal_id=%s AND space_id=%s AND status='active'
                ORDER BY updated_at DESC
                """,
                (
                    self.workspace_id,
                    self.principal_id,
                    space_id,
                ),
            ).fetchall()
        best: tuple[int, dict[str, Any]] | None = None
        for row in rows:
            page = self._decode_page(dict(row))
            related, score = self._topic_relation(
                topics, page_title=page["title"], page_aliases=page["aliases"]
            )
            if not related:
                continue
            if best is None or score > best[0]:
                best = (score, page)
        return best[1] if best else None

    @classmethod
    def _topic_relation(
        cls,
        topics: list[str],
        *,
        page_title: str,
        page_aliases: list[str],
    ) -> tuple[bool, int]:
        normalized_topics = {cls._normalize_title(value) for value in topics}
        normalized_page = {
            cls._normalize_title(value) for value in [page_title, *page_aliases]
        }
        if normalized_topics.intersection(normalized_page):
            return True, 100
        query_tokens = cls._topic_tokens(" ".join(topics))
        page_tokens = cls._topic_tokens(f"{page_title} {' '.join(page_aliases)}")
        shared = query_tokens.intersection(page_tokens)
        strong = {
            token
            for token in shared
            if len(token) >= 4
            and token.isascii()
            and token
            not in {"agent", "coding", "code", "project", "system", "interview"}
        }
        chinese = {token for token in shared if not token.isascii()}
        memory_pair = "agent" in shared and "记忆" in chinese
        related = (
            memory_pair
            or len(strong) >= 2
            or (bool(strong) and len(chinese) >= 1)
            or len(chinese) >= 3
        )
        return related, len(strong) * 4 + len(chinese) + (8 if memory_pair else 0)

    @staticmethod
    def _topic_tokens(value: str) -> set[str]:
        lowered = value.casefold()
        words = {
            token
            for token in re.findall(r"[a-z0-9]+", lowered)
            if len(token) >= 3 and token not in {"the", "and", "with", "from"}
        }
        chinese_runs = re.findall(r"[\u4e00-\u9fff]+", lowered)
        bigrams = {
            run[index : index + 2]
            for run in chinese_runs
            for index in range(max(0, len(run) - 1))
        }
        bigrams.difference_update(
            {
                "来源",
                "视频",
                "材料",
                "内容",
                "整理",
                "相关",
                "可以",
                "适用",
                "需要",
                "当前",
                "通过",
                "一个",
                "一种",
                "以及",
                "没有",
                "进行",
            }
        )
        return words.union(bigrams)

    @staticmethod
    def _scope(space: dict[str, Any]) -> SourceScope:
        return SourceScope(
            source_db_ids=frozenset(int(value) for value in space["source_ids"]),
            video_ids=frozenset(int(value) for value in space.get("video_ids", [])),
            all_active=bool(space["all_active"]),
        )

    def _ensure_dirty(self, connection: Any, video_id: int, *, conn=None) -> int:
        conn = connection if conn is None else conn
        row = connection.execute(
            "SELECT dirty_generation FROM assistant_source_dirty WHERE assistant_source_dirty.workspace_id=%s AND video_id=%s",
            (
                self.workspace_id,
                video_id,
            ),
        ).fetchone()
        if row is None:
            connection.execute(
                "INSERT INTO assistant_source_dirty(workspace_id,video_id, dirty_generation, updated_at) VALUES(%s,%s, 1, %s)",
                (
                    self.workspace_id,
                    video_id,
                    utc_now(),
                ),
            )
            return 1
        return int(row["dirty_generation"])

    def _enqueue_reconcile(
        self,
        connection: Any,
        video_id: int,
        generation: int,
        *,
        batch_id: str | None = None,
        task_subset: list[int] | None = None,
        conn=None,
    ) -> str:
        conn = connection if conn is None else conn
        batch_scope = {}
        if batch_id:
            row = connection.execute(
                "SELECT b.space_id,s.scope_version FROM assistant_maintenance_batches b JOIN assistant_spaces s ON s.id=b.space_id WHERE b.workspace_id=%s AND b.id=%s",
                (
                    self.workspace_id,
                    batch_id,
                ),
            ).fetchone()
            if row:
                batch_scope = {
                    "space_id": row["space_id"],
                    "scope_version": row["scope_version"],
                }
        return self.store.enqueue_job(
            connection,
            kind="source_reconcile",
            dedupe_key=f"source_reconcile:{video_id}:{generation}"
            + (f":batch:{batch_id}" if batch_id else ""),
            payload={
                "video_id": video_id,
                "dirty_generation": generation,
                **batch_scope,
                **({"task_subset": task_subset} if task_subset else {}),
                **({"maintenance_batch_id": batch_id} if batch_id else {}),
            },
        )

    def _budgeted_provider(
        self,
        payload: dict[str, Any],
        provider: StructuredProvider,
        *,
        job=None,
        conn=None,
    ) -> StructuredProvider:
        batch_id = payload.get("maintenance_batch_id")

        def allowed():
            self._require_publish_allowed()
            self._require_maintenance_authorized(payload)

        return BudgetedStructuredProvider(
            self.store,
            str(batch_id) if batch_id else None,
            provider,
            continue_allowed=allowed,
            job=job,
        )

    @staticmethod
    def _card_material(snapshot: dict[str, Any]) -> tuple[str, str]:
        materials = snapshot["materials"]
        selected = next(
            (
                (kind, str(materials[kind]))
                for kind in ("summary", "raw_subtitle", "transcript")
                if materials.get(kind)
            ),
            None,
        )
        notes = "\n\n".join(
            f"[已有注释 id={item['id']}；作者身份未核实；更新于 {item.get('updated_at') or '未知'}]\n{item['content']}"
            for item in snapshot.get("notes", [])
            if str(item.get("content") or "").strip()
        )
        description = str(snapshot["metadata"].get("description") or "")
        sections = []
        if selected:
            sections.append(f"[材料视图：{selected[0]}]\n{selected[1]}")
        if description:
            sections.append(f"[视频简介；上传者提供，非逐字字幕]\n{description}")
        if notes:
            sections.append(f"[已有注释；不能直接当成当前用户立场]\n{notes}")
        return "\n\n".join(sections), (
            f"{selected[0]}_and_notes"
            if selected and notes
            else selected[0]
            if selected
            else "metadata_and_notes"
        )

    @staticmethod
    def _card_input_hash(snapshot: dict[str, Any]) -> str:
        value = f"{snapshot['metadata_hash']}:{snapshot['content_hash']}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _card_body_equivalent(
        old: dict[str, Any], new: dict[str, Any], old_card: dict[str, Any]
    ) -> bool:
        if old.get("content_hash") != new.get("content_hash"):
            return False
        time_fields = {"published_at", "metadata_observed_at", "discovered_at"}
        old_identity = {
            key: value
            for key, value in old.get("metadata", {}).items()
            if key not in time_fields
        }
        new_identity = {
            key: value
            for key, value in new.get("metadata", {}).items()
            if key not in time_fields
        }
        # Historical SQLite Snapshots contain JSON text; PG JSONB returns a
        # list. Compare that one representation structurally, without changing
        # either immutable Snapshot or ignoring genuine link differences.
        for identity in (old_identity, new_identity):
            links = identity.get("description_links_json")
            if isinstance(links, str):
                try:
                    links = json.loads(links)
                except (ValueError, TypeError):
                    return False
                if not isinstance(links, list):
                    return False
                identity["description_links_json"] = links
            elif links is not None and not isinstance(links, list):
                return False
        if old_identity != new_identity:
            return False
        if old.get("metadata", {}).get("published_at") != new.get("metadata", {}).get(
            "published_at"
        ):
            body = json.dumps(
                {
                    "summary": old_card.get("summary"),
                    "key_points": old_card.get("key_points"),
                },
                ensure_ascii=False,
            )
            if re.search(r"\b(?:19|20)\d{2}\b", body):
                return False
        return True

    @classmethod
    def _normalize_card(
        cls, response: dict[str, Any], snapshot: dict[str, Any], material_kind: str
    ) -> dict[str, Any]:
        points = []
        material, material_kind_actual = cls._card_material(snapshot)
        note_content = "\n".join(
            str(note.get("content") or "") for note in snapshot.get("notes", [])
        )
        for item in response.get("key_points", [])[:8]:
            if (
                not isinstance(item, dict)
                or not str(item.get("markdown") or "").strip()
            ):
                continue
            assessment = str(item.get("assessment") or "source_reported")
            quote = str(item.get("evidence_quote") or "").strip()[:500]
            position = material.find(quote) if quote else -1
            if assessment == "user_annotation" and (
                not quote or quote not in note_content
            ):
                assessment = "source_reported"
            cited_source = str(item.get("cited_source") or "").strip()[:200]
            if (
                (cited_source and cited_source not in material)
                or not cls._reference_like(cited_source)
                or re.search(
                    r"视频章节|视频简介|视频字幕|\d{2}:\d{2}:\d{2}", cited_source
                )
            ):
                cited_source = ""
            points.append(
                {
                    "heading": str(item.get("heading") or "关键观点")[:120],
                    "markdown": str(item["markdown"]).strip()[:6000],
                    "applicability": str(item.get("applicability") or "")[:500],
                    "assessment": assessment
                    if assessment in {"source_reported", "user_annotation"}
                    else "source_reported",
                    "evidence_quote": quote if position >= 0 else "",
                    "position": {"start": position, "end": position + len(quote)}
                    if position >= 0
                    else None,
                    "material_view": material_kind_actual,
                    "speaker": "",  # A video's uploader does not establish who speaks.
                    "cited_source": cited_source if position >= 0 else "",
                    "cited_source_checked": False,
                }
            )
        metadata = snapshot["metadata"]
        return {
            "title": str(metadata.get("title") or "未命名材料"),
            "uploader": str(metadata.get("uploader") or ""),
            "published_at": metadata.get("published_at"),
            "memberships": snapshot["memberships"],
            "coverage": snapshot["coverage"],
            "material_kind": material_kind,
            "material_views": [
                kind
                for kind in ("summary", "raw_subtitle", "transcript")
                if snapshot["materials"].get(kind)
            ],
            "annotation_count": len(snapshot.get("notes", [])),
            "metadata_observed_at": metadata.get("metadata_observed_at"),
            "summary": str(response.get("summary") or "").strip()[:3000],
            "key_points": points,
            "topics": [
                str(value).strip()[:120]
                for value in response.get("topics", [])[:5]
                if str(value).strip()
            ],
            "limitations": [
                str(value).strip()[:500]
                for value in response.get("limitations", [])[:5]
                if str(value).strip()
            ],
        }

    @classmethod
    def _normalize_wiki_patch(
        cls,
        response: dict[str, Any],
        *,
        topic: str,
        card: dict[str, Any],
        revision: str,
        source_key_map: dict[str, str] | None = None,
        source_titles: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        page_type = str(response.get("page_type") or "topic")
        if page_type not in {"concept", "method", "comparison", "topic"}:
            page_type = "topic"

        def public_text(value: Any, limit: int) -> str:
            clean = str(value or "").strip()[:limit]
            for key, title in (source_titles or {}).items():
                clean = re.sub(
                    rf"(?<![A-Za-z0-9]){re.escape(key)}(?![A-Za-z0-9])",
                    f"《{title[:80]}》",
                    clean,
                )
            clean = re.sub(r"key=(《[^》]+》)", r"\1", clean)
            clean = re.sub(r"coverage=[a-z_]+", "当前可用材料", clean)
            clean = re.sub(r"material_kind=[a-z_]+", "摘要材料视图", clean)
            return clean

        blocks = []
        all_keyed = True
        for item in response.get("blocks", [])[:5]:
            if (
                not isinstance(item, dict)
                or not str(item.get("markdown") or "").strip()
            ):
                continue
            keys = item.get("source_keys")
            if source_key_map and isinstance(keys, list):
                if not keys or any(str(key) not in source_key_map for key in keys):
                    continue
                source_revisions = list(
                    dict.fromkeys(source_key_map[str(key)] for key in keys)
                )
            else:
                all_keyed = False
                source_revisions = [revision]
            quote = str(item.get("evidence_quote") or "").strip()[:500]
            supporting_point = next(
                (
                    point
                    for point in card.get("key_points", [])
                    if quote and point.get("evidence_quote") == quote
                ),
                None,
            )
            assessment = str(item.get("assessment") or "source_reported")
            if assessment == "user_annotation" and (
                supporting_point is None
                or supporting_point.get("assessment") != "user_annotation"
            ):
                assessment = "source_reported"
            if assessment not in {"source_reported", "user_annotation"}:
                assessment = "system_synthesis"
            blocks.append(
                {
                    "heading": public_text(item.get("heading") or card["title"], 120),
                    "markdown": public_text(item["markdown"], 12000),
                    "applicability": public_text(item.get("applicability"), 500),
                    "assessment": assessment,
                    "relation": public_text(item.get("relation") or "related", 100),
                    "speaker": "",
                    "cited_source": (
                        str(supporting_point.get("cited_source") or "")
                        if supporting_point
                        and cls._reference_like(
                            str(supporting_point.get("cited_source") or "")
                        )
                        else ""
                    ),
                    "evidence_quote": quote if supporting_point else "",
                    "material_view": str(
                        supporting_point.get("material_view")
                        or card.get("material_kind")
                        or ""
                    )
                    if supporting_point
                    else str(card.get("material_kind") or ""),
                    "position": supporting_point.get("position")
                    if supporting_point
                    else None,
                    "source_refs": source_revisions,
                }
            )
        return {
            "title": str(response.get("title") or topic).strip()[:200],
            "page_type": page_type,
            "summary": public_text(
                response.get("summary") or card.get("summary"), 3000
            ),
            "blocks": blocks,
            "replace_derived": bool(blocks and all_keyed),
            "source_title": card["title"],
            "revision": revision,
        }

    @classmethod
    def _blocks_with_identity(
        cls, blocks: list[dict[str, Any]], *, revision: str, topic: str
    ) -> list[dict[str, Any]]:
        values = []
        for index, block in enumerate(blocks):
            source_refs = list(
                dict.fromkeys(
                    str(value) for value in block.get("source_refs", [revision])
                )
            )
            stable = hashlib.sha256(
                f"{topic}:{cls.COMPILER_VERSION}:{index}:{','.join(sorted(source_refs))}".encode(
                    "utf-8"
                )
            ).hexdigest()[:20]
            values.append(
                {
                    "stable_id": f"wblock_{stable}",
                    "heading": str(block.get("heading") or "来源说明"),
                    "markdown": str(block.get("markdown") or ""),
                    "source_refs": source_refs,
                    "applicability": str(block.get("applicability") or ""),
                    "assessment": str(block.get("assessment") or "source_reported"),
                    "relation": str(block.get("relation") or "related"),
                    "speaker": str(block.get("speaker") or ""),
                    "cited_source": str(block.get("cited_source") or ""),
                    "cited_source_checked": False,
                    "evidence_quote": str(block.get("evidence_quote") or ""),
                    "material_view": str(block.get("material_view") or ""),
                    "position": block.get("position"),
                    "manual_lock": False,
                    "compiler_version": cls.COMPILER_VERSION,
                }
            )
        return values

    @staticmethod
    def _page_for_prompt(
        page: dict[str, Any] | None, *, source_key_map: dict[str, str] | None = None
    ) -> dict[str, Any] | None:
        if page is None:
            return None
        revision_keys = {
            revision: key for key, revision in (source_key_map or {}).items()
        }
        return {
            "title": page["title"],
            "summary": page["summary"],
            "version": page["version"],
            "availability": page.get("availability", "full"),
            "blocks": [
                {
                    "heading": block["heading"],
                    "markdown": block["markdown"][:1500],
                    "manual_lock": bool(block.get("manual_lock")),
                    "assessment": block.get("assessment") or "source_reported",
                    "content_origin": "personal_note"
                    if block.get("assessment") == "user_explicit"
                    else "source",
                    "source_keys": [
                        revision_keys[ref]
                        for ref in block.get("source_refs", [])
                        if ref in revision_keys
                    ],
                }
                for block in page["blocks"][-8:]
            ],
        }

    @staticmethod
    def _normalize_title(value: str) -> str:
        return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.casefold())[:200]

    @staticmethod
    def _decode_page(value: dict[str, Any]) -> dict[str, Any]:
        value = row_dto(value, timestamps={"created_at", "updated_at"})
        value["aliases"] = value.pop("aliases_json")
        value["blocks"] = value.pop("blocks_json")
        return value
