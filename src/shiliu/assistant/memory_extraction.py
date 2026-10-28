"""Existing extraction policy, PG Job/dispatch ledger and atomic fact publication.

Assistant run state/HTTP scheduling remain W10. This is the P3 maintenance edge.
"""

from __future__ import annotations
import asyncio
import re
from typing import Any
from shiliu.assistant.memory_policy import forbids_auto_save, plausible_personal_excerpt
from shiliu.assistant.memory_time import has_personal_candidate, checked_validity
from shiliu.assistant.wiki import (
    BudgetedStructuredProvider,
    ModelOutcomeUnknown,
    MaintenanceYield,
)
from shiliu.storage.scheduler import (
    claim_job,
    job_transition,
    guard_job,
    recover_job,
    _lane,
)
from shiliu.storage.fences import CoordinationConflict
from shiliu.assistant.runtime_contract import ModelBudgetWait
from shiliu.assistant.lease_renewal import job_renewal, renewal_period


class MemoryExtractionService:
    def __init__(self, memories, *, provider_factory, continue_allowed=None):
        self.memories = memories
        self.db = memories.db
        self.store = memories.store
        self.extraction_provider_factory = provider_factory
        self.continue_allowed = continue_allowed

    def _maintenance_idle(self):
        return self.continue_allowed() if self.continue_allowed is not None else True

    def _require_maintenance_idle(self, conn=None):
        if not self._maintenance_idle():
            raise MaintenanceYield("maintenance_user_returned")

    def _model_proposals(self, job, prompt):
        with self.db.connect(read_only=True) as c:
            if c.execute(
                "SELECT dispatch_id FROM model_dispatch_receipts WHERE workspace_id=%s AND principal_id=%s AND job_id=%s",
                (self.db.workspace_id, self.db.context.user_id, job["id"]),
            ).fetchone():
                raise ModelOutcomeUnknown(
                    "memory_extraction_dispatched_without_staged_result"
                )
        delegate = self.extraction_provider_factory()

        class Adapter:
            def generate_json(self, *, system, prompt, max_tokens):
                return delegate.extract_memories(prompt=prompt)

        return BudgetedStructuredProvider(
            self.store,
            None,
            Adapter(),
            job=job,
            continue_allowed=self._require_maintenance_idle,
        ).generate_json(system="Memory extraction policy", prompt=prompt)

    async def process(self, job):
        result = await self._prepare_and_apply(job)
        with self.db.connect() as c:
            row = c.execute(
                "SELECT status FROM assistant_jobs WHERE workspace_id=%s AND id=%s",
                (self.db.workspace_id, job["id"]),
            ).fetchone()
            if row["status"] != "completed":
                self.store.finish_job(
                    job["id"],
                    owner=job["lease_owner"],
                    lease_epoch=job["lease_epoch"],
                    proposal=result,
                    conn=c,
                )
        return result

    async def _prepare_and_apply(self, job: dict[str, Any]) -> dict[str, Any]:
        payload = job["payload"]

        def policy_matches(conn=None) -> bool:
            policy = self.memories.auto_policy(conn=conn)
            return (
                payload.get("auto_enabled_at_enqueue") is True
                and policy["enabled"]
                and int(payload.get("auto_memory_generation", -1))
                == policy["generation"]
            )

        if not policy_matches():
            return {
                "proposals": [],
                "applied_memory_ids": [],
                "reason": "automatic_memory_policy_changed",
            }
        context = self.store.get_thread(str(payload["thread_id"]))
        message_ids = set(str(value) for value in payload["message_ids"])
        user_messages = [
            item
            for item in context["messages"]
            if item["id"] in message_ids and item["role"] == "user"
        ]
        if not user_messages:
            return {
                "proposals": [],
                "applied_memory_ids": [],
                "reason": "no_unprocessed_user_messages",
            }
        eligible_messages = [
            item
            for item in user_messages
            if not forbids_auto_save(str(item["content"]))
        ]
        if not eligible_messages:
            return {
                "proposals": [],
                "applied_memory_ids": [],
                "processed_message_ids": list(message_ids),
                "reason": "user_forbids_auto_save",
            }
        if not has_personal_candidate(eligible_messages):
            return {
                "proposals": [],
                "applied_memory_ids": [],
                "processed_message_ids": list(message_ids),
                "reason": "no_personal_background_candidate",
            }
        raw_user = "\n".join(
            f"{item['id']} [{item['created_at']}]: {item['content']}"
            for item in user_messages
        )
        user_text = "\n".join(str(item["content"]) for item in eligible_messages)
        thread_space = self.store.get_space(int(context["space_id"]))
        message_positions = [
            index
            for index, item in enumerate(context["messages"])
            if item["id"] in message_ids
        ]
        nearby: list[str] = []
        if message_positions:
            start = max(0, min(message_positions) - 2)
            for item in context["messages"][start : min(message_positions)]:
                nearby.append(
                    f"{item['role']} [{item['created_at']}]: {str(item['content'])[:2000]}"
                )
        nearby_text = "\n".join(nearby) if nearby else "（无）"
        related = self.memories.recall(
            user_text[:300], space_id=int(context["space_id"]), limit=5
        )
        related_text = (
            "\n".join(
                f"{item['id']} v{item['version']} [{item['kind']}] {item['text']}"
                for item in related
            )
            or "（无）"
        )
        prompt = (
            "从以下用户消息中提取最多 5 条可跨会话使用的个人背景。"
            "用户无需说‘记住’：例如‘今天确定接下来三周主要补数据库基础’是可保存的阶段目标，"
            "应输出 op=add、kind=context、scope_kind=space 的提案；本轮格式要求才输出空列表。"
            "有日期或持续时长的目标需要保留时间依据；正在比较只能记为探索状态，不得写成决定。"
            "视频/文档观点、引用内容、工具结果和助手回答不得成为用户立场。"
            "‘我不同意 X’不等于采用 X；‘我决定采用 X’才是明确决定。"
            "邻近上下文只用于解释指代，source_excerpt 必须逐字来自本次用户消息。"
            "事件时间（下个月、下周开始、过段时间）不是 Memory 到期日，无时间也可保存。只有用户明确记忆适用期限时，可返回带时区的 valid_from/expires_at、validity_note 和"
            "validity_timezone；无法可靠确定精确时间时只保留 validity_note，不猜时间。"
            '返回 {"proposals":[{op,kind,text,subject_key,scope_kind,scope_id,'
            "source_excerpt,target_memory_id?,expected_version?,valid_from?,expires_at?,"
            "validity_note?,validity_timezone?}]}。scope 默认 space，时区默认 Asia/Shanghai。\n"
            f"当前 Space id={thread_space['id']} name={thread_space['name']}。"
            f"\n相关现有正式记忆（修订须给出这里的 ID 和版本）：\n{related_text}"
            f"\n邻近解释上下文：\n{nearby_text}"
            f"\n本次用户消息：\n{raw_user}"
        )
        staged = job.get("proposal") or {}
        if "proposals" in staged:
            proposals = staged["proposals"]
        else:
            proposals = await asyncio.to_thread(self._model_proposals, job, prompt)
        from shiliu.assistant.lease_renewal import check_renewal

        check_renewal()
        saved_proposal = {"proposals": proposals}
        if not self.store.save_job_proposal(
            str(job["id"]),
            saved_proposal,
            owner=str(job["lease_owner"]),
            lease_epoch=int(job["lease_epoch"]),
        ):
            raise RuntimeError("job_lease_lost")
        if not self._maintenance_idle():
            raise MaintenanceYield("maintenance_user_returned")
        if not policy_matches():
            return {
                "proposals": proposals,
                "applied_memory_ids": [],
                "reason": "automatic_memory_policy_changed",
            }
        with self.memories._memory_write_transaction(job=job) as publish_conn:
            targets = sorted(
                {
                    str(p["target_memory_id"])
                    for p in proposals[:5]
                    if p.get("target_memory_id")
                }
            )
            if targets:
                publish_conn.execute(
                    "SELECT id FROM assistant_memories WHERE workspace_id=%s AND principal_id=%s AND id=ANY(%s) ORDER BY id FOR UPDATE",
                    (self.db.workspace_id, self.db.context.user_id, targets),
                ).fetchall()
            applied: list[str] = []
            for index, proposal in enumerate(proposals[:5]):
                if not self._maintenance_idle():
                    raise MaintenanceYield("maintenance_user_returned")
                if not policy_matches(conn=publish_conn):
                    break
                excerpt = str(proposal.get("source_excerpt") or "")
                if (
                    not excerpt
                    or excerpt not in user_text
                    or not plausible_personal_excerpt(
                        excerpt, str(proposal.get("kind") or "context")
                    )
                ):
                    continue
                source = next(
                    (
                        item
                        for item in eligible_messages
                        if excerpt in str(item["content"])
                    ),
                    None,
                )
                if source is None:
                    continue
                full_source = str(source["content"])
                excerpt_start = full_source.find(excerpt)
                lead = full_source[max(0, excerpt_start - 100) : excerpt_start]
                lead_clause = re.split(r"[，。；;,\n]", lead)[-1]
                tail = full_source[
                    excerpt_start + len(excerpt) : excerpt_start + len(excerpt) + 24
                ]
                if re.search(
                    r"引用|假设|比如|例如|视频里|作者说|讲者说|有人说|转述|例句|不是我的决定",
                    lead_clause,
                ) or re.search(
                    r"不是我(?:的)?(?:决定|计划|偏好)|只是引用|只是例子|是个假设", tail
                ):
                    continue
                later = [
                    item
                    for item in self.store.get_thread(
                        str(payload["thread_id"]), conn=publish_conn
                    )["messages"]
                    if item["role"] == "user" and int(item["seq"]) > int(source["seq"])
                ]
                excerpt_terms = set(re.findall(r"[\u4e00-\u9fff]{2,}", excerpt))
                excerpt_pairs = {
                    term[index : index + 2]
                    for term in excerpt_terms
                    for index in range(len(term) - 1)
                }
                subject_key = str(proposal.get("subject_key") or "")
                if any(
                    re.search(
                        r"撤回|取消|不再|改主意|先别|不要记|并未决定|没有决定",
                        str(item["content"]),
                    )
                    and (
                        bool(subject_key and subject_key in str(item["content"]))
                        or bool(
                            excerpt_pairs.intersection(
                                {
                                    term[index : index + 2]
                                    for term in re.findall(
                                        r"[\u4e00-\u9fff]{2,}", str(item["content"])
                                    )
                                    for index in range(len(term) - 1)
                                }
                            )
                        )
                        or bool(
                            re.search(
                                r"刚才|之前|上述|那个|这项|这个决定|这条|改主意",
                                str(item["content"]),
                            )
                        )
                    )
                    for item in later
                ):
                    continue
                try:
                    time_bounds = checked_validity(
                        excerpt,
                        str(source["created_at"]),
                        {
                            key: proposal[key]
                            for key in ("valid_from", "expires_at")
                            if key in proposal
                        },
                    )
                except ValueError:
                    continue
                proposal.update(time_bounds)
                proposal["stated_at"] = str(source["created_at"])
                if str(proposal.get("op")) == "revise":
                    if not any(
                        str(item["id"]) == str(proposal.get("target_memory_id"))
                        and int(item["version"])
                        == int(proposal.get("expected_version") or 0)
                        for item in related
                    ):
                        continue
                requested_scope = str(proposal.get("scope_kind") or "space")
                global_markers = ("以后默认", "长期", "所有项目", "跨项目")
                if requested_scope != "user" or not any(
                    marker in excerpt for marker in global_markers
                ):
                    proposal["scope_kind"] = "space"
                    proposal["scope_id"] = int(thread_space["id"])
                value = self.memories.apply_extracted(
                    proposal,
                    source_message_ids=[str(source["id"])],
                    expected_epoch=int(payload["memory_epoch"]),
                    operation_key=f"extract:{job['id']}:{index}",
                    expected_auto_generation=int(
                        payload.get("auto_memory_generation", -1)
                    ),
                    publish_guard=self._require_maintenance_idle,
                    _connection=publish_conn,
                    job=job,
                )
                if value is not None:
                    applied.append(str(value["id"]))
            result = {
                "proposals": proposals,
                "applied_memory_ids": applied,
                "processed_message_ids": [str(item["id"]) for item in user_messages],
                "message_cursor": payload.get("message_cursor"),
                "reason": (
                    "applied"
                    if applied
                    else "automatic_memory_policy_changed"
                    if not policy_matches(conn=publish_conn)
                    else "no_admissible_proposal"
                ),
            }
            self.store.finish_job(
                job["id"],
                owner=job["lease_owner"],
                lease_epoch=job["lease_epoch"],
                proposal=result,
                conn=publish_conn,
            )
            return result


class MemoryExtractionWorker:
    def __init__(
        self,
        memories,
        *,
        owner,
        provider_factory,
        continue_allowed=None,
        lease_seconds=120,
        heartbeat_interval=None,
    ):
        self.memories = memories
        self.db = memories.db
        self.owner = owner
        self.lease_seconds = lease_seconds
        self.heartbeat_interval = renewal_period(lease_seconds, heartbeat_interval)
        self.service = MemoryExtractionService(
            memories,
            provider_factory=provider_factory,
            continue_allowed=continue_allowed,
        )

    def recover(self):
        count = 0
        with self.db.connect() as c:
            rows = c.execute(
                "SELECT id FROM assistant_jobs WHERE workspace_id=%s AND principal_id=%s AND kind='memory_extract' AND status='running' ORDER BY id",
                (self.db.workspace_id, self.db.context.user_id),
            ).fetchall()
        for row in rows:
            with self.db.connect(guard=True) as c:
                # Classify only while holding the same lane -> Job locks as recovery.
                _lane(c, self.db.context)
                job = c.execute(
                    "SELECT proposal_json FROM assistant_jobs WHERE id=%s FOR UPDATE",
                    (row["id"],),
                ).fetchone()
                dispatched = c.execute(
                    "SELECT 1 FROM model_dispatch_receipts WHERE workspace_id=%s AND principal_id=%s AND job_id=%s",
                    (self.db.workspace_id, self.db.context.user_id, row["id"]),
                ).fetchone()
                disposition = (
                    "staged"
                    if job["proposal_json"] is not None
                    else "unknown"
                    if dispatched
                    else "replay_safe"
                )
                count += int(
                    recover_job(c, self.db.context, row["id"], disposition=disposition)
                )
                self.memories.store.notify_job_issue(c, row["id"])
        return count

    def run_once(self):
        with self.db.connect() as c:
            raw = claim_job(
                c,
                self.db.context,
                self.owner,
                kinds=("memory_extract",),
                lease_seconds=self.lease_seconds,
                activity_allowed=self.service._maintenance_idle(),
            )
        if raw is None:
            return None
        job = self.memories.store.job_dto(raw)
        try:
            with job_renewal(
                self.db,
                job,
                lease_seconds=self.lease_seconds,
                interval=self.heartbeat_interval,
            ):
                return asyncio.run(self.service.process(job))
        except CoordinationConflict:
            return {"status": "stale", "reason": "job_fenced"}
        except (MaintenanceYield, ModelBudgetWait) as exc:
            reason = "activity" if isinstance(exc, MaintenanceYield) else "daily_budget"
            try:
                self.memories.store.defer_maintenance_job(job, reason=reason)
            except CoordinationConflict:
                return {"status": "stale", "reason": "job_fenced"}
            return {
                "status": "queued" if reason == "activity" else "budget_wait",
                "reason": reason,
            }
        except Exception as exc:
            try:
                with self.db.connect() as c:
                    guard_job(
                        c, self.db.context, job["id"], self.owner, job["lease_epoch"]
                    )
                    job_transition(
                        c,
                        self.db.context,
                        job["id"],
                        self.owner,
                        job["lease_epoch"],
                        action="fail",
                    )
                    if isinstance(exc, ModelOutcomeUnknown):
                        c.execute(
                            "UPDATE assistant_jobs SET status='blocked',last_error_code='external_result_unknown' WHERE id=%s",
                            (job["id"],),
                        )
                    self.memories.store.notify_job_issue(c, job["id"])
            except CoordinationConflict:
                return {"status": "stale", "reason": "job_fenced"}
            return {
                "status": "blocked"
                if isinstance(exc, ModelOutcomeUnknown)
                else "retry_wait",
                "error_code": type(exc).__name__,
            }
