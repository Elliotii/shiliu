"""Thin result index. Writers receive the caller connection and trusted identities.

No transaction, source lookup, history scan or provider call belongs in record().
Domain readers remain responsible for redaction and business-action eligibility.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone

from psycopg.types.json import Jsonb
from shiliu.assistant.runtime_contract import AssistantConflict

CAUSE_KEYS = frozenset(
    {
        "thread_id",
        "run_id",
        "request_message_id",
        "source_message_ids",
        "job_id",
        "video_id",
        "snapshot_revision",
        "operation_key",
        "receipt_key",
        "supersedes_message_id",
    }
)


def message_id(context, event_key):
    return (
        "an_"
        + hashlib.sha256(
            f"{context.workspace_id}:{context.user_id}:{event_key}".encode()
        ).hexdigest()[:40]
    )


def plan_fingerprint(plan):
    payload = plan.get("payload", plan.get("payload_json", {}))
    # UI labels and outcomes are projections, never candidate identity.
    topics = [
        {k: v for k, v in t.items() if k not in {"source_labels"}}
        for t in payload.get("topics", [])
    ]
    if not topics or not plan.get("source_message_id"):
        return None
    value = {
        "topics": topics,
        "omitted": payload.get("omitted", []),
        "scope_version": plan["scope_version"],
        "source_message_id": plan["source_message_id"],
        "save_request": {
            k: v
            for k, v in payload.get("save_request", {}).items()
            if k
            in {
                "answer_message_ids",
                "answer_message_id",
                "answer_run_id",
                "user_message_ids",
                "request_message_id",
                "source_message_id",
            }
        },
    }
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def record(
    c,
    context,
    *,
    event_key,
    origin_type,
    origin_id,
    source_type,
    space_id=None,
    origin_version=None,
    cause_refs=None,
    effect_refs=None,
    created_at=None,
    read_at=None,
    activity_at=None,
):
    causes = cause_refs or {}
    if causes.keys() - CAUSE_KEYS:
        raise ValueError("unsupported_notification_cause")
    now = created_at or datetime.now(timezone.utc)
    identity = message_id(context, event_key)
    c.execute(
        """INSERT INTO assistant_notifications
        (id,workspace_id,principal_id,space_id,event_key,origin_type,origin_id,origin_version,
         source_type,cause_refs,effect_refs,created_at,activity_at,read_at)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(workspace_id,principal_id,event_key) DO NOTHING""",
        (
            identity,
            context.workspace_id,
            context.user_id,
            space_id,
            event_key,
            origin_type,
            str(origin_id),
            origin_version,
            source_type,
            Jsonb(causes),
            Jsonb([]),
            now,
            now,
            read_at,
        ),
    )
    if effect_refs:
        c.execute(
            """UPDATE assistant_notifications SET effect_refs=
            (SELECT jsonb_agg(DISTINCT x) FROM jsonb_array_elements(effect_refs || %s) x),
            activity_at=%s WHERE workspace_id=%s AND principal_id=%s AND id=%s
            AND NOT effect_refs @> %s""",
            (
                Jsonb(effect_refs),
                activity_at or now,
                context.workspace_id,
                context.user_id,
                identity,
                Jsonb(effect_refs),
            ),
        )
    return identity


def plan_record(c, context, plan, *, effect_refs=None, previous=None):
    fingerprint = plan_fingerprint(plan)
    payload = plan.get("payload", plan.get("payload_json", {}))
    results = plan.get("results", plan.get("results_json", {}))
    needs_repair = any(v.get("status") == "failed" for v in results.values())
    if not fingerprint or (
        payload.get("direct_authorized") and not effect_refs and not needs_repair
    ):
        return None
    previous_fingerprint = plan_fingerprint(previous) if previous else None
    changed = previous_fingerprint and previous_fingerprint != fingerprint
    saved_request = payload.get("save_request", {})
    fact_ids = list(
        dict.fromkeys(
            saved_request.get("user_message_ids", [])
            + saved_request.get("answer_message_ids", [])
            + (
                [saved_request["answer_message_id"]]
                if saved_request.get("answer_message_id")
                else []
            )
        )
    )
    causes = {
        "request_message_id": plan["source_message_id"],
        "source_message_ids": fact_ids or [plan["source_message_id"]],
    }
    if changed:
        causes["supersedes_message_id"] = message_id(
            context, f"plan:{plan['id']}:{previous_fingerprint}"
        )
    return record(
        c,
        context,
        event_key=f"plan:{plan['id']}:{fingerprint}",
        origin_type="plan_revision",
        origin_id=plan["id"],
        origin_version=fingerprint,
        space_id=plan["space_id"],
        source_type="dialogue",
        cause_refs=causes,
        created_at=datetime.now(timezone.utc) if changed else plan["created_at"],
        effect_refs=effect_refs,
        activity_at=plan["updated_at"],
    )


def proposal_record(c, context, proposal, *, effect_refs=None):
    return record(
        c,
        context,
        event_key=f"wiki-proposal:{proposal['id']}",
        origin_type="wiki_proposal",
        origin_id=proposal["id"],
        space_id=proposal["space_id"],
        source_type="video" if proposal["kind"] == "source_patch" else "manual",
        cause_refs=(
            {
                "job_id": proposal["payload_json"]["origin_job_id"],
                "video_id": proposal["payload_json"]["video_id"],
                "snapshot_revision": proposal["payload_json"]["revision"],
            }
            if proposal["kind"] == "source_patch"
            else None
        ),
        created_at=proposal["created_at"],
        effect_refs=effect_refs,
        activity_at=proposal["updated_at"],
    )


class NotificationService:
    def __init__(self, runtime):
        self.runtime = runtime
        self.store, self.db = runtime.store, runtime.store.db
        self.context = self.db.context

    def _rows(self, c, *, history=False):
        args = (self.context.workspace_id, self.context.user_id)
        persisted = [
            dict(r)
            for r in c.execute(
                "SELECT * FROM assistant_notifications WHERE workspace_id=%s AND principal_id=%s",
                args,
            )
        ]
        seen = {r["id"] for r in persisted}
        # Compatibility is read-only. No activation-time bulk backfill.
        candidates = []
        for row in c.execute(
            "SELECT * FROM assistant_knowledge_plans WHERE workspace_id=%s AND principal_id=%s AND status IN ('pending','partial')",
            args,
        ):
            p = dict(row)
            f = plan_fingerprint(p)
            if f and not p["payload_json"].get("direct_authorized"):
                candidates.append(
                    self._virtual(
                        f"plan:{p['id']}:{f}", "plan_revision", p, "dialogue", f
                    )
                )
        for row in c.execute(
            "SELECT * FROM assistant_wiki_proposals WHERE workspace_id=%s AND principal_id=%s AND kind IN ('merge','source_patch') AND status='pending'",
            args,
        ):
            p = dict(row)
            candidates.append(
                self._virtual(f"wiki-proposal:{p['id']}", "wiki_proposal", p, "manual")
            )
        activation = c.execute(
            "SELECT value::timestamptz AS at FROM assistant_runtime_state WHERE workspace_id=%s AND principal_id=%s AND key='messages_activation_at'",
            args,
        ).fetchone()
        if activation:
            for row in c.execute(
                "SELECT * FROM assistant_jobs WHERE workspace_id=%s AND principal_id=%s AND created_at<%s AND status IN ('blocked','failed') AND kind IN ('source_reconcile','source_extract','wiki_integrate','memory_extract','memory_index','memory_purge')",
                args + (activation["at"],),
            ):
                p = dict(row)
                p["space_id"] = (p["payload_json"] or {}).get("space_id")
                candidates.append(
                    self._virtual(f"job-issue:{p['id']}", "job_issue", p, "system")
                )
            for row in c.execute(
                "SELECT r.*,t.space_id FROM assistant_runs r JOIN assistant_threads t ON (t.workspace_id,t.id)=(r.workspace_id,r.thread_id) WHERE r.workspace_id=%s AND t.principal_id=%s AND r.created_at<%s AND r.status='failed' AND r.working_state_json ? 'knowledge_save'",
                args + (activation["at"],),
            ):
                p = dict(row)
                candidates.append(
                    self._virtual(f"run-issue:{p['id']}", "run_issue", p, "system")
                )
        if history:
            for kind, table, owner in [
                ("wiki_change", "assistant_wiki_changes", "assistant_wiki_pages"),
                ("memory_change", "assistant_memory_changes", "assistant_memories"),
            ]:
                field = "page_id" if kind == "wiki_change" else "memory_id"
                # Creation retraction is represented by the original message's
                # exact undo_ref. Seconds DTOs may precede the activation marker;
                # that does not turn its bookkeeping change into another message.
                standalone = (
                    " AND ch.operation<>'creation_retracted'"
                    if kind == "memory_change"
                    else ""
                )
                for row in c.execute(
                    f"""SELECT ch.*, obj.principal_id FROM {table} ch JOIN {owner} obj ON obj.id=ch.{field} AND obj.workspace_id=ch.workspace_id
                    WHERE ch.workspace_id=%s AND obj.principal_id=%s AND ch.created_at < COALESCE((SELECT value::timestamptz FROM assistant_runtime_state WHERE workspace_id=%s AND principal_id=%s AND key='messages_activation_at'),'-infinity'){standalone}""",
                    args + args,
                ):
                    p = dict(row)
                    candidates.append(
                        self._virtual(
                            f"{kind.replace('_', '-')}:{p['id']}",
                            kind,
                            p,
                            "system",
                            read=True,
                        )
                    )
        # Never generate a completed virtual row for the effects of a candidate.
        covered = {str(e.get("id")) for r in persisted for e in r["effect_refs"]}
        return persisted + [
            r
            for r in candidates
            if r["id"] not in seen
            and not (
                r["origin_type"].endswith("_change") and str(r["origin_id"]) in covered
            )
        ]

    def _virtual(self, key, kind, obj, source, version=None, read=False):
        return dict(
            id=message_id(self.context, key),
            workspace_id=self.context.workspace_id,
            principal_id=self.context.user_id,
            space_id=obj.get("space_id"),
            event_key=key,
            origin_type=kind,
            origin_id=str(obj["id"]),
            origin_version=version,
            source_type=source,
            cause_refs={"source_message_ids": [obj["source_message_id"]]}
            if kind == "plan_revision"
            else {"job_id": obj["id"]}
            if kind == "job_issue"
            else {},
            effect_refs=[],
            undo_ref=None,
            created_at=obj["created_at"],
            activity_at=obj["created_at"],
            read_at=obj["created_at"] if read else None,
        )

    def _owned(self, c, table, identity):
        if table == "assistant_runs":
            return c.execute(
                "SELECT r.* FROM assistant_runs r JOIN assistant_threads t ON (t.workspace_id,t.id)=(r.workspace_id,r.thread_id) WHERE r.workspace_id=%s AND t.principal_id=%s AND r.id=%s",
                (self.context.workspace_id, self.context.user_id, identity),
            ).fetchone()
        return c.execute(
            f"SELECT * FROM {table} WHERE workspace_id=%s AND principal_id=%s AND id=%s",
            (self.context.workspace_id, self.context.user_id, identity),
        ).fetchone()

    def _resolve(self, c, row, detail=False):
        r = dict(row)
        kind = r["origin_type"]
        state = "unavailable"
        refs = []
        actions = []
        body = None
        reason = None
        links = []
        applied = None
        source_times = []
        processing = []
        label = None
        summary = None
        requires_confirmation = False
        object_type = "memory" if kind == "memory_change" else "wiki"
        resolution = None
        if kind in {"wiki_change", "memory_change"}:
            wiki = kind == "wiki_change"
            table = "assistant_wiki_changes" if wiki else "assistant_memory_changes"
            ch = c.execute(
                f"SELECT * FROM {table} WHERE workspace_id=%s AND id=%s",
                (self.context.workspace_id, r["origin_id"]),
            ).fetchone()
            if ch:
                obj_id = ch["page_id" if wiki else "memory_id"]
                obj = self._owned(
                    c, "assistant_wiki_pages" if wiki else "assistant_memories", obj_id
                )
                if obj:
                    r["space_id"] = (
                        obj["space_id"]
                        if wiki
                        else None
                        if obj["scope_kind"] == "user"
                        else int(obj["scope_id"])
                    )
                    summary = {
                        "created": "新建记忆",
                        "corrected": "更正记忆",
                        "forgotten": "遗忘记忆",
                        "adopted": "采纳记忆",
                        "discussion_saved": "保存讨论成果",
                        "source_rebound": "更新来源版本",
                        "associate": "更新材料关联",
                    }.get(ch["operation"], ch["operation"])
                    label = (
                        obj["title"]
                        if wiki
                        else "所有对话"
                        if obj["scope_kind"] == "user"
                        else "当前范围记忆"
                    )
                    state = "undone" if r["undo_ref"] else "applied"
                    applied = ch["created_at"]
                    refs = [
                        {
                            "type": "wiki" if wiki else "memory",
                            "id": obj_id,
                            "space_id": obj.get("space_id"),
                            "version": ch["version"],
                        }
                    ]
                    if wiki:
                        links.append(
                            {"kind": "wiki", "id": obj_id, "space_id": obj["space_id"]}
                        )
                        body = (
                            self.runtime.wiki.notification_change(
                                c, dict(ch), dict(obj)
                            )
                            if detail
                            else None
                        )
                        if body:
                            from urllib.parse import urlparse

                            for source in body.get("sources", []):
                                url = source["url"]
                                host = urlparse(url or "").hostname or ""
                                if urlparse(url or "").scheme == "https" and (
                                    host == "bilibili.com"
                                    or host.endswith(".bilibili.com")
                                    or host == "b23.tv"
                                ):
                                    link = {
                                        "kind": "video",
                                        "url": url,
                                        "snapshot_revision": source["source_revision"],
                                    }
                                    if link not in links:
                                        links.append(link)
                                if source["published_at"]:
                                    source_times.append(
                                        {
                                            "kind": "video_published",
                                            "at": datetime.fromtimestamp(
                                                source["published_at"], timezone.utc
                                            ),
                                        }
                                    )
                        if detail and not r["undo_ref"]:
                            try:
                                actions.append(
                                    self.runtime.wiki.notification_undo_eligibility(
                                        c, ch, obj
                                    )
                                )
                            except AssistantConflict as exc:
                                reason = str(exc)
                    else:
                        links.append(
                            {
                                "kind": "memory",
                                "id": obj_id,
                                "space_id": None
                                if obj["scope_kind"] == "user"
                                else int(obj["scope_id"]),
                            }
                        )
                        if obj[
                            "status"
                        ] != "forgotten" and self.runtime.memories._is_currently_valid(
                            dict(obj)
                        ):
                            label = str(obj["text"])[:70]
                            body = (
                                {"before": ch["before_json"], "after": ch["after_json"]}
                                if detail
                                else None
                            )
                        else:
                            reason = "记忆已遗忘，历史正文不可用"
                        key = r["cause_refs"].get("operation_key")
                        if (
                            detail
                            and key
                            and ch["operation"] == "created"
                            and not r["undo_ref"]
                        ):
                            try:
                                self.runtime.memories._creation_for_undo(
                                    c, obj_id, key, int(ch["version"]), lock=False
                                )
                                actions.append(
                                    {"kind": "undo", "expected_version": ch["version"]}
                                )
                            except AssistantConflict as exc:
                                reason = str(exc)
                    if not actions:
                        reason = reason or "此效果没有可证明安全的消息撤销"
        elif kind == "plan_revision":
            obj = self._owned(c, "assistant_knowledge_plans", r["origin_id"])
            if obj:
                label = "讨论保存计划"
                plan = self.runtime.wiki._decode_knowledge_plan(dict(obj))
                current = plan_fingerprint(plan) == r["origin_version"]
                state = (
                    {
                        "completed": "applied",
                        "rejected": "rejected",
                        "partial": "partial",
                        "pending": "pending",
                    }.get(plan["status"], "expired")
                    if current
                    else "expired"
                )
                outcomes = plan["results"] if current else {}
                if not current:
                    saved = c.execute(
                        "SELECT result_json FROM assistant_mutation_receipts WHERE workspace_id=%s AND principal_id=%s AND operation_key=%s",
                        (
                            self.context.workspace_id,
                            self.context.user_id,
                            f"plan-content:{plan['id']}:{r['origin_version']}",
                        ),
                    ).fetchone()
                    historical = saved["result_json"] if saved else None
                    if not historical:
                        receipts = c.execute(
                            "SELECT result_json FROM assistant_mutation_receipts WHERE workspace_id=%s AND principal_id=%s AND operation IN ('knowledge_plan_revise','knowledge_plan_replace') AND result_json->>'id'=%s",
                            (
                                self.context.workspace_id,
                                self.context.user_id,
                                plan["id"],
                            ),
                        ).fetchall()
                        historical = next(
                            (
                                x["result_json"]
                                for x in receipts
                                if plan_fingerprint(x["result_json"])
                                == r["origin_version"]
                            ),
                            None,
                        )
                    if historical:
                        plan = historical
                        outcomes = plan.get("results", {})
                    else:
                        plan = {**plan, "payload": {"topics": [], "omitted": []}}
                    if any(x.get("status") == "completed" for x in outcomes.values()):
                        state = "partial"
                refs = [
                    {
                        "type": "wiki",
                        "id": v["page_id"],
                        "version": v["version"],
                        "space_id": plan["space_id"],
                    }
                    for v in outcomes.values()
                    if v.get("status") == "completed"
                ]
                links.append(
                    {"kind": "plan", "id": plan["id"], "space_id": plan["space_id"]}
                )
                candidate_view = self.runtime.wiki.notification_plan(c, plan)
                requires_confirmation = (
                    current
                    and not plan["payload"].get("direct_authorized")
                    and state in {"pending", "partial"}
                    and candidate_view.get("confirmable", False)
                )
                if state == "pending" and not requires_confirmation:
                    state = "expired"
                if detail:
                    body = candidate_view
                    if (
                        current
                        and state in {"pending", "partial"}
                        and body.get("confirmable")
                    ):
                        actions = [
                            {
                                "kind": "plan_preview",
                                "id": plan["id"],
                                "space_id": plan["space_id"],
                                "expected_version": plan["version"],
                            }
                        ]
                if not current:
                    reason = "审核内容已被替代；成功项保留原生效事实"
        elif kind == "wiki_proposal":
            obj = self._owned(c, "assistant_wiki_proposals", r["origin_id"])
            if obj and obj["kind"] in {"merge", "source_patch"}:
                label = (
                    "视频正文修改建议"
                    if obj["kind"] == "source_patch"
                    else "Wiki 合并提案"
                )
                state = {
                    "pending": "pending",
                    "accepted": "applied",
                    "rejected": "rejected",
                    "stale": "expired",
                }[obj["status"]]
                if obj["kind"] == "source_patch":
                    d = obj["payload_json"]
                    r["cause_refs"].update(
                        job_id=d["origin_job_id"],
                        video_id=d["video_id"],
                        snapshot_revision=d["revision"],
                    )
                links.append(
                    {
                        "kind": "wiki",
                        "id": obj["target_page_id"],
                        "space_id": obj["space_id"],
                    }
                )
                candidate_view = self.runtime.wiki.notification_proposal(c, dict(obj))
                requires_confirmation = state == "pending" and candidate_view.get(
                    "confirmable", False
                )
                if state == "pending" and not requires_confirmation:
                    state = "expired"
                if detail:
                    body = candidate_view
                    if (
                        obj["kind"] == "source_patch"
                        and state == "applied"
                        and len(r["effect_refs"]) == 1
                    ):
                        effect = c.execute(
                            "SELECT * FROM assistant_wiki_changes WHERE workspace_id=%s AND id=%s",
                            (self.context.workspace_id, r["effect_refs"][0]["id"]),
                        ).fetchone()
                        current = self._owned(
                            c, "assistant_wiki_pages", obj["target_page_id"]
                        )
                        if effect and current:
                            body = {
                                **candidate_view,
                                **self.runtime.wiki.notification_change(
                                    c, dict(effect), dict(current)
                                ),
                            }
                    if state == "pending" and body.get("confirmable"):
                        actions = [
                            {
                                "kind": "proposal",
                                "id": obj["id"],
                                "space_id": obj["space_id"],
                                **(
                                    {
                                        "expected_content_version": obj[
                                            "content_version"
                                        ],
                                        "expected_target_version": obj[
                                            "target_version"
                                        ],
                                    }
                                    if obj["kind"] == "source_patch"
                                    else {}
                                ),
                            }
                        ]
                    if obj["kind"] == "source_patch":
                        actions.append(
                            {
                                "kind": "proposal_refresh",
                                "id": obj["id"],
                                "space_id": obj["space_id"],
                            }
                        )
                refs = [
                    {
                        "type": "wiki",
                        "id": obj["target_page_id"],
                        "space_id": obj["space_id"],
                        "version": obj["target_version"],
                    }
                ]
        elif kind in {"job_issue", "run_issue"}:
            obj = self._owned(
                c,
                "assistant_jobs" if kind == "job_issue" else "assistant_runs",
                r["origin_id"],
            )
            if obj:
                resolved = obj["status"] in {"completed", "succeeded", "cancelled"}
                state = "applied" if resolved else "important_failure"
                resolution = (
                    "resolved"
                    if resolved
                    else "retrying"
                    if obj["status"]
                    in {"queued", "running", "retry_wait", "budget_wait"}
                    else "unresolved"
                )
                if kind == "job_issue" and obj["kind"].startswith("memory_"):
                    object_type = "memory"
                reason = (
                    obj.get("last_error_code") or obj.get("error_code") or "执行失败"
                )
        effect_objects = []
        for effect_ref in r["effect_refs"]:
            if effect_ref.get("type") != "wiki_change":
                continue
            effect = c.execute(
                "SELECT ch.page_id,ch.version,ch.created_at,p.space_id FROM assistant_wiki_changes ch JOIN assistant_wiki_pages p ON (p.workspace_id,p.id)=(ch.workspace_id,ch.page_id) WHERE ch.workspace_id=%s AND p.principal_id=%s AND ch.id=%s",
                (self.context.workspace_id, self.context.user_id, effect_ref["id"]),
            ).fetchone()
            if effect:
                effect_objects.append(
                    {
                        "type": "wiki",
                        "id": effect["page_id"],
                        "space_id": effect["space_id"],
                        "version": effect["version"],
                    }
                )
                link = {
                    "kind": "wiki",
                    "id": effect["page_id"],
                    "space_id": effect["space_id"],
                }
                if link not in links:
                    links.append(link)
                applied = (
                    max(applied, effect["created_at"])
                    if applied
                    else effect["created_at"]
                )
        if effect_objects:
            refs = effect_objects
            if kind == "plan_revision" and state == "expired":
                state = "partial"
        if (
            detail
            and kind == "plan_revision"
            and not r["undo_ref"]
            and len(r["effect_refs"]) == 1
            and r["effect_refs"][0].get("type") == "wiki_change"
        ):
            change = c.execute(
                "SELECT * FROM assistant_wiki_changes WHERE workspace_id=%s AND id=%s",
                (self.context.workspace_id, r["effect_refs"][0]["id"]),
            ).fetchone()
            obj = (
                self._owned(c, "assistant_wiki_pages", change["page_id"])
                if change
                else None
            )
            if obj:
                try:
                    actions.append(
                        self.runtime.wiki.notification_undo_eligibility(c, change, obj)
                    )
                except AssistantConflict as exc:
                    reason = str(exc)
        if r["undo_ref"]:
            state = "undone"
        if detail and not actions and state == "applied" and not reason:
            reason = (
                "多效果结果未接入逐项消息撤销；请查看当前对象和原管理入口"
                if len(refs) > 1
                else "此结果没有可证明安全的消息撤销；请查看当前对象和原管理入口"
            )
        for mid in r["cause_refs"].get("source_message_ids", []) + (
            [r["cause_refs"]["request_message_id"]]
            if r["cause_refs"].get("request_message_id")
            else []
        ):
            m = c.execute(
                """SELECT m.id,m.created_at,m.thread_id,t.space_id FROM assistant_messages m JOIN assistant_threads t ON t.id=m.thread_id AND t.workspace_id=m.workspace_id WHERE m.workspace_id=%s AND t.principal_id=%s AND m.id=%s""",
                (self.context.workspace_id, self.context.user_id, mid),
            ).fetchone()
            if m:
                links.append(
                    {"kind": "thread", "id": m["thread_id"], "space_id": m["space_id"]}
                )
                source_times.append({"kind": "dialogue", "at": m["created_at"]})
        vid = r["cause_refs"].get("video_id")
        if vid and r["space_id"]:
            from urllib.parse import urlparse

            space = self.store.get_space(r["space_id"], conn=c)
            if int(vid) in self.runtime.wiki.sources.visible_video_ids(
                self.runtime.wiki._scope(space), conn=c
            ):
                video = c.execute(
                    "SELECT video_url,published_at FROM videos WHERE workspace_id=%s AND id=%s",
                    (self.context.workspace_id, vid),
                ).fetchone()
                if video:
                    url = video["video_url"]
                    host = urlparse(url or "").hostname or ""
                    if urlparse(url or "").scheme == "https" and (
                        host == "bilibili.com"
                        or host.endswith(".bilibili.com")
                        or host == "b23.tv"
                    ):
                        links.append(
                            {
                                "kind": "video",
                                "url": url,
                                "snapshot_revision": r["cause_refs"].get(
                                    "snapshot_revision"
                                ),
                            }
                        )
                    if video["published_at"]:
                        source_times.append(
                            {
                                "kind": "video_published",
                                "at": datetime.fromtimestamp(
                                    video["published_at"], timezone.utc
                                ),
                            }
                        )
        jid = r["cause_refs"].get("job_id")
        if jid:
            job = self._owned(c, "assistant_jobs", jid)
            if job:
                processing = [
                    {"kind": k, "at": job[k]}
                    for k in ("started_at", "completed_at")
                    if job.get(k)
                ]
        r.update(
            origin_ref={
                "type": kind,
                "id": r["origin_id"],
                "version": r["origin_version"],
            },
            object_refs=refs,
            object_type=object_type,
            resolution=resolution,
            object_label=label or "业务记录",
            change_summary=summary,
            business_state=state,
            requires_confirmation=requires_confirmation,
            actions=actions,
            links=links,
            source_times=source_times,
            processing_times=processing,
            applied_at=applied,
            reason=reason,
        )
        if detail:
            r["detail"] = body
        return r

    def list(
        self,
        *,
        view="all",
        object_type=None,
        source_type=None,
        space_id=None,
        unread_only=False,
        show_history=False,
        limit=20,
        cursor=None,
    ):
        filters = [view, object_type, source_type, space_id, unread_only, show_history]
        stamp = hashlib.sha256(json.dumps(filters).encode()).hexdigest()[:20]
        after = None
        if cursor:
            try:
                token = json.loads(
                    base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
                )
                if token[0] != stamp:
                    raise ValueError()
                if len(token) != 4:
                    raise ValueError()
                after = (token[1], token[2], token[3])
            except Exception as exc:
                raise ValueError("invalid_message_cursor") from exc
        with self.db.pg.transaction(read_only=True, isolation="repeatable read") as c:
            if space_id:
                self.store.get_space(space_id, conn=c)
            values = [self._resolve(c, r) for r in self._rows(c, history=show_history)]
            unread = sum(
                1
                for v in values
                if v["read_at"] is None and (not space_id or v["space_id"] == space_id)
            )
            cutoff = datetime.now(timezone.utc) - timedelta(days=7)

            def visible(v):
                state = v["business_state"]
                if space_id and v["space_id"] != space_id:
                    return False
                if object_type and v["object_type"] != object_type:
                    return False
                if source_type and v["source_type"] != source_type:
                    return False
                if unread_only and v["read_at"] is not None:
                    return False
                if view == "pending" and not v.get("requires_confirmation"):
                    return False
                if view == "updated" and state != "applied":
                    return False
                if view == "issues" and state not in {"important_failure", "partial"}:
                    return False
                activity = v["activity_at"]
                activity = (
                    datetime.fromisoformat(activity)
                    if isinstance(activity, str)
                    else activity
                )
                return (
                    show_history
                    or v["read_at"] is None
                    or state in {"pending", "partial", "important_failure"}
                    or (state == "applied" and activity >= cutoff)
                )

            values = [v for v in values if visible(v)]

            def sort_key(v):
                group = (
                    2
                    if v.get("requires_confirmation")
                    else 1
                    if v["read_at"] is None
                    or v["business_state"] in {"partial", "important_failure"}
                    else 0
                )
                at = v["activity_at"]
                at = datetime.fromisoformat(at) if isinstance(at, str) else at
                return (group, at.isoformat(), v["id"])

            values.sort(key=sort_key, reverse=True)
            if after:
                values = [v for v in values if sort_key(v) < after]
            page = values[:limit]
            nxt = None
            if len(values) > limit:
                last = page[-1]
                nxt = (
                    base64.urlsafe_b64encode(
                        json.dumps([stamp, *sort_key(last)]).encode()
                    )
                    .decode()
                    .rstrip("=")
                )
            return {"items": page, "next_cursor": nxt, "unread_count": unread}

    def get(self, identity):
        with self.db.pg.transaction(read_only=True, isolation="repeatable read") as c:
            for row in self._rows(c, history=True):
                if row["id"] == identity:
                    return self._resolve(c, row, True)
        raise KeyError(identity)

    def read(self, ids):
        with self.db.connect(guard=True) as c:
            rows = {r["id"]: r for r in self._rows(c, history=True)}
            if any(i not in rows for i in ids):
                raise KeyError("message")
            for i in ids:
                r = rows[i]
                record(
                    c,
                    self.context,
                    event_key=r["event_key"],
                    origin_type=r["origin_type"],
                    origin_id=r["origin_id"],
                    origin_version=r["origin_version"],
                    space_id=r["space_id"],
                    source_type=r["source_type"],
                    created_at=r["created_at"],
                    cause_refs=r["cause_refs"],
                )
                c.execute(
                    "UPDATE assistant_notifications SET read_at=COALESCE(read_at,clock_timestamp()) WHERE workspace_id=%s AND principal_id=%s AND id=%s",
                    (self.context.workspace_id, self.context.user_id, i),
                )
        return {"read_ids": ids}

    def undo(self, identity, *, expected_version, operation_key):
        row = self.get(identity)
        if row["undo_ref"] == operation_key:
            return {"undo_ref": operation_key, "already_undone": True}
        if not any(a["kind"] == "undo" for a in row["actions"]):
            raise AssistantConflict(row["reason"] or "message_undo_unavailable")
        effect = row["object_refs"][0]
        if expected_version != effect["version"]:
            raise AssistantConflict("message_effect_version_conflict")
        if row["origin_type"] == "plan_revision" and len(row["effect_refs"]) == 1:
            return self.runtime.wiki.undo_notification_change(
                identity,
                row["effect_refs"][0]["id"],
                expected_version=expected_version,
                operation_key=operation_key,
            )
        if row["origin_type"] == "wiki_change":
            return self.runtime.wiki.undo_notification_change(
                identity,
                row["origin_id"],
                expected_version=expected_version,
                operation_key=operation_key,
            )
        return self.runtime.memories.undo_created(
            effect["id"],
            save_operation_key=row["cause_refs"]["operation_key"],
            expected_version=expected_version,
            operation_key=operation_key,
            _notification_id=identity,
        )
