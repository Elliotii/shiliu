from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from contextlib import nullcontext
from datetime import datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from shiliu.assistant.snapshots import CapturedSource
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.memory_policy import anchored_validity, has_time_reference
from shiliu.assistant.sources import CollectionSourceService, SourceScope
from shiliu.assistant.store import AssistantConflict, AssistantRunStore, ModelBudgetWait
from shiliu.db import Database, utc_now


class StructuredProvider(Protocol):
    def generate_json(self, *, system: str, prompt: str, max_tokens: int = 2400) -> dict[str, Any]: ...


class MaintenanceBudgetExceeded(RuntimeError):
    code = "maintenance_budget_exhausted"


class BudgetedStructuredProvider:
    def __init__(
        self, store: AssistantRunStore | Database, batch_id: str | None, delegate: StructuredProvider,
        *, daily_limit: int = 60,
    ) -> None:
        self.store = store if isinstance(store, AssistantRunStore) else AssistantRunStore(store)
        self.db = self.store.db
        self.batch_id = batch_id
        self.delegate = delegate
        self.daily_limit = daily_limit

    def generate_json(self, *, system: str, prompt: str, max_tokens: int = 2400) -> dict[str, Any]:
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
            now = utc_now()
            connection.execute(
                """
                INSERT OR IGNORE INTO assistant_model_budget_days(
                    budget_date,lane,request_limit,requests_used,updated_at
                ) VALUES(?, 'background', ?, 0, ?)
                """,
                (today, self.daily_limit, now),
            )
            daily = connection.execute(
                """
                UPDATE assistant_model_budget_days
                SET requests_used=requests_used+1, request_limit=?, updated_at=?
                WHERE budget_date=? AND lane='background' AND requests_used<?
                """,
                (self.daily_limit, now, today, self.daily_limit),
            )
            if daily.rowcount != 1:
                raise ModelBudgetWait("后台模型每日额度已用完，等待下一个本地自然日")
            if self.batch_id:
                updated = connection.execute(
                    "UPDATE assistant_maintenance_batches SET calls_used=calls_used+1 "
                    "WHERE id=? AND calls_used<model_limit", (self.batch_id,),
                )
                if updated.rowcount != 1:
                    raise MaintenanceBudgetExceeded("本批后台模型请求预算已耗尽")
        started = time.monotonic()
        try:
            response = self.delegate.generate_json(
                system=system, prompt=prompt, max_tokens=max_tokens
            )
        except BaseException:
            self.store.record_model_usage(
                lane="background", usage=None, outcome="error_or_lost",
                latency_ms=(time.monotonic() - started) * 1000,
            )
            raise
        self.store.record_model_usage(
            lane="background", usage=None, outcome="response_usage_unavailable",
            latency_ms=(time.monotonic() - started) * 1000,
        )
        return response


class WikiService:
    EXTRACTION_VERSION = "source-card-v2"
    COMPILER_VERSION = "wiki-compiler-v7"

    @staticmethod
    def _reference_like(value: str) -> bool:
        """Only label a named work or document as a cited source, never gear."""
        return bool(re.search(
            r"论文|文档|报告|文章|书籍|指南|白皮书|标准|规范|研究|官网|官方原文|"
            r"\b(?:paper|study|report|documentation|guide|specification)\b",
            value, re.IGNORECASE,
        ) or len(re.findall(r"[A-Za-z]{3,}", value)) >= 5)

    def __init__(
        self,
        *,
        db: Database,
        store: AssistantRunStore,
        sources: CollectionSourceService,
        principal_id: str = "local_operator",
    ) -> None:
        self.db = db
        self.store = store
        self.sources = sources
        self.principal_id = principal_id

    def bootstrap_space(self, space_id: int, *, limit: int = 5, model_budget: int = 30) -> dict[str, Any]:
        if not 1 <= limit <= 10 or not 1 <= model_budget <= 30:
            raise ValueError("invalid_maintenance_budget")
        space = self.store.get_space(space_id)
        video_ids = self.sources.visible_video_ids(
            self._scope(space), order="collected_desc"
        )[: max(1, min(limit, 10))]
        jobs: list[str] = []
        batch_id = f"amb_{uuid.uuid4().hex}"
        with self.db.connect() as connection:
            connection.execute(
                "INSERT INTO assistant_maintenance_batches(id,space_id,source_limit,model_limit,calls_used,created_at) "
                "VALUES(?,?,?,?,0,?)",
                (batch_id, space_id, limit, model_budget, utc_now()),
            )
            for video_id in video_ids:
                generation = self._ensure_dirty(connection, video_id)
                jobs.append(self._enqueue_reconcile(connection, video_id, generation, batch_id=batch_id))
        return {"space_id": space_id, "queued": len(jobs), "video_ids": video_ids,
                "job_ids": jobs, "batch_id": batch_id, "source_limit": limit,
                "model_budget": model_budget}

    def request_topic(
        self, *, space_id: int, topic: str, source_refs: list[str],
        request_key: str, source_message_id: str | None = None,
    ) -> dict[str, Any]:
        """Queue an explicit, bounded request through the ordinary source pipeline."""
        topic = topic.strip()
        if not topic or len(topic) > 120 or not 1 <= len(source_refs) <= 5:
            raise ValueError("invalid_topic_request")
        space = self.store.get_space(space_id)
        scope = self._scope(space)
        if not self.sources.source_refs_visible(source_refs, scope):
            raise ValueError("source_out_of_scope")
        video_ids = []
        for ref in source_refs:
            parts = str(ref).split(":", 2)
            if len(parts) < 2 or parts[0] != "video" or not parts[1].isdigit():
                raise ValueError("invalid_source_ref")
            video_ids.append(int(parts[1]))
        if len(set(video_ids)) != len(video_ids):
            raise ValueError("duplicate_source_ref")
        stable_request = f"{space_id}:{hashlib.sha256(request_key.encode('utf-8')).hexdigest()[:24]}"
        jobs = []
        with self.db.connect() as connection:
            for video_id in video_ids:
                generation = self._ensure_dirty(connection, video_id)
                jobs.append(self.store.enqueue_job(
                    connection, kind="source_reconcile",
                    dedupe_key=f"topic_request:{stable_request}:{video_id}",
                    payload={
                        "video_id": video_id, "dirty_generation": generation,
                        "space_id": space_id, "scope_version": space["scope_version"],
                        "task_topic": topic, "request_key": stable_request,
                        **({"source_message_id": source_message_id} if source_message_id else {}),
                    },
                ))
            states = [str(connection.execute(
                "SELECT status FROM assistant_jobs WHERE id=?", (job_id,),
            ).fetchone()["status"]) for job_id in jobs]
        status = "accepted"
        if any(value in {"waiting_budget", "blocked"} for value in states):
            status = "waiting_budget"
        elif all(value == "succeeded" for value in states):
            page = self._find_page(space_id, topic)
            linked_ids = {
                int(ref.split(":", 2)[1]) for ref in
                self.history_source_refs(str(page["id"]), space_id=space_id)
            } if page and page.get("blocks") else set()
            status = "already_available" if set(video_ids).issubset(linked_ids) else "no_change"
        return {"status": status, "topic": topic, "queued": sum(
            value in {"queued", "running", "retry_wait"} for value in states
        ), "job_ids": jobs}

    def reconcile(self, job: dict[str, Any]) -> dict[str, Any]:
        payload = job["payload"]
        video_id = int(payload["video_id"])
        generation = int(payload["dirty_generation"])
        with self.db.connect() as connection:
            current = connection.execute(
                "SELECT dirty_generation FROM assistant_source_dirty WHERE video_id=?",
                (video_id,),
            ).fetchone()
        if current is not None and int(current["dirty_generation"]) > generation:
            return {"superseded": True, "reason": "newer_source_generation"}
        if payload.get("request_key"):
            space = self.store.get_space(int(payload["space_id"]))
            if int(space["scope_version"]) != int(payload["scope_version"]):
                return {"superseded": True, "reason": "scope_version_changed"}
            if video_id not in self.sources.visible_video_ids(self._scope(space)):
                return {"superseded": True, "reason": "source_out_of_scope"}
        captured = self.sources.snapshots.capture(video_id)
        with self.db.connect() as connection:
            job_id = self.store.enqueue_job(
                connection,
                kind="source_extract",
                dedupe_key=f"source_extract:{captured.revision}:{self.EXTRACTION_VERSION}" + (
                    f":batch:{payload['maintenance_batch_id']}" if payload.get("maintenance_batch_id") else ""
                ) + (f":task:{payload['request_key']}" if payload.get("request_key") else ""),
                payload={
                    "video_id": video_id,
                    "revision": captured.revision,
                    "dirty_generation": generation,
                    "extraction_version": self.EXTRACTION_VERSION,
                    **({"maintenance_batch_id": payload["maintenance_batch_id"]}
                       if payload.get("maintenance_batch_id") else {}),
                    **({"task_topic": payload["task_topic"], "request_key": payload["request_key"],
                        **({"source_message_id": payload["source_message_id"]}
                           if payload.get("source_message_id") else {})}
                       if payload.get("request_key") else {}),
                },
            )
        return {"revision": captured.revision, "source_extract_job_id": job_id}

    def extract_source_card(
        self, job: dict[str, Any], *, provider: StructuredProvider
    ) -> dict[str, Any]:
        payload = job["payload"]
        provider = self._budgeted_provider(payload, provider)
        revision = str(payload["revision"])
        video_id = int(payload["video_id"])
        with self.db.connect() as connection:
            card_row = connection.execute(
                "SELECT extraction_version FROM assistant_source_cards WHERE revision=?",
                (revision,),
            ).fetchone()
        existing = self.get_source_card(revision) if card_row and card_row["extraction_version"] == self.EXTRACTION_VERSION else None
        if existing is not None:
            self._enqueue_integrations(video_id, revision, batch_id=payload.get("maintenance_batch_id"),
                                       task_topic=payload.get("task_topic"), request_key=payload.get("request_key"),
                                       source_message_id=payload.get("source_message_id"))
            return {"reused": True, "revision": revision}
        captured = self.sources._capture_or_load(video_id, revision)
        snapshot = captured.snapshot
        input_hash = self._card_input_hash(snapshot)
        with self.db.connect() as connection:
            reusable = connection.execute(
                """
                SELECT card_json FROM assistant_source_cards
                WHERE video_id=? AND input_hash=? AND extraction_version=?
                ORDER BY updated_at DESC LIMIT 1
                """,
                (video_id, input_hash, self.EXTRACTION_VERSION),
            ).fetchone()
            time_candidates = connection.execute(
                """SELECT c.revision,c.card_json FROM assistant_source_cards c
                JOIN assistant_source_revisions r ON r.revision=c.revision
                WHERE c.video_id=? AND r.content_hash=? AND c.extraction_version=?
                ORDER BY c.updated_at DESC LIMIT 8""",
                (video_id, snapshot["content_hash"], self.EXTRACTION_VERSION),
            ).fetchall() if reusable is None else []
        if reusable is not None:
            card = json.loads(reusable["card_json"])
            card["memberships"] = snapshot["memberships"]
            card["metadata_observed_at"] = snapshot["metadata"].get("metadata_observed_at")
        else:
            time_reuse = next((
                json.loads(item["card_json"]) for item in time_candidates
                if self._card_body_equivalent(
                    self.sources._capture_or_load(video_id, str(item["revision"])).snapshot,
                    snapshot, json.loads(item["card_json"]),
                )
            ), None)
            if time_reuse is not None:
                card = dict(time_reuse)
                card["published_at"] = snapshot["metadata"].get("published_at")
                card["memberships"] = snapshot["memberships"]
                card["metadata_observed_at"] = snapshot["metadata"].get("metadata_observed_at")
                self._commit_source_card(captured, input_hash=input_hash, card=card)
                integration_jobs = self._enqueue_integrations(
                    video_id, revision, batch_id=payload.get("maintenance_batch_id"),
                    task_topic=payload.get("task_topic"), request_key=payload.get("request_key"),
                    source_message_id=payload.get("source_message_id"),
                )
                return {"revision": revision, "reused_time_only": True,
                        "integration_job_ids": integration_jobs, "card": card}
            material, material_kind = self._card_material(snapshot)
            if not material.strip():
                response = {
                    "summary": "", "key_points": [], "topics": [],
                    "limitations": ["只有标题或空简介，未生成内容结论"],
                }
            else:
                chunks = [material[index:index + 12000] for index in range(0, len(material), 12000)]
                cursor = max(0, int(payload.get("batch_cursor", 0)))
                stop = min(len(chunks), cursor + 4)
                for batch_index in range(cursor, stop):
                    response = self._extract_batch(
                        provider, snapshot=snapshot, material_kind=material_kind,
                        material=chunks[batch_index], batch_index=batch_index,
                        batch_total=len(chunks),
                    )
                    self._save_card_batch(
                        revision, batch_index=batch_index,
                        input_hash=hashlib.sha256(chunks[batch_index].encode("utf-8")).hexdigest(),
                        response=response,
                    )
                if stop < len(chunks):
                    with self.db.connect() as connection:
                        continuation = self.store.enqueue_job(
                            connection,
                            kind="source_extract",
                            dedupe_key=(
                                f"source_extract:{revision}:{self.EXTRACTION_VERSION}:batch:{stop}"
                                + (f":maintenance:{payload['maintenance_batch_id']}"
                                   if payload.get("maintenance_batch_id") else "")
                            ),
                            payload={**payload, "batch_cursor": stop},
                        )
                    return {
                        "partial": True, "revision": revision,
                        "processed_batches": stop, "batch_total": len(chunks),
                        "continuation_job_id": continuation,
                    }
                response = self._merge_card_batches(revision)
            card = self._normalize_card(response, snapshot, material_kind)
        self._commit_source_card(captured, input_hash=input_hash, card=card)
        integration_jobs = self._enqueue_integrations(video_id, revision, batch_id=payload.get("maintenance_batch_id"),
                                                      task_topic=payload.get("task_topic"), request_key=payload.get("request_key"),
                                                      source_message_id=payload.get("source_message_id"))
        return {"revision": revision, "integration_job_ids": integration_jobs, "card": card}

    def integrate_source_card(
        self, job: dict[str, Any], *, provider: StructuredProvider
    ) -> dict[str, Any]:
        payload = job["payload"]
        provider = self._budgeted_provider(payload, provider)
        space = self.store.get_space(int(payload["space_id"]))
        if int(space["scope_version"]) != int(payload["scope_version"]):
            return {"superseded": True, "reason": "scope_version_changed"}
        video_id = int(payload["video_id"])
        if video_id not in self.sources.visible_video_ids(self._scope(space)):
            return {"superseded": True, "reason": "source_out_of_scope"}
        revision = str(payload["revision"])
        with self.db.connect() as connection:
            head = connection.execute(
                """SELECT current_revision FROM assistant_source_heads
                WHERE principal_id=? AND video_id=?""",
                (self.principal_id, video_id),
            ).fetchone()
        if head is None or str(head["current_revision"] or "") != revision:
            return {"superseded": True, "reason": "source_revision_changed"}
        card = self.get_source_card(revision)
        if card is None:
            raise RuntimeError("source_card_missing")
        if not card.get("summary") and not card.get("key_points"):
            return {"no_change": True, "reason": "insufficient_material", "revision": revision}
        topic = str(payload.get("task_topic") or payload.get("topic") or
                    (card.get("topics") or [card["title"]])[0]).strip() or card["title"]
        existing = self._find_page(int(space["id"]), topic)
        if payload.get("repair_page_id") and (
            existing is None or str(existing["id"]) != str(payload["repair_page_id"])
        ):
            return {"superseded": True, "reason": "repair_page_changed"}
        fuzzy_candidate = existing is None
        if existing is None and not payload.get("task_topic"):
            existing = self._find_related_page(int(space["id"]), {**card, "topics": [topic]})
        current_existing = self._visible_page(existing) if existing is not None else None
        visible_block_ids = {str(block["stable_id"]) for block in
                             (current_existing or {}).get("blocks", [])}
        if existing is not None:
            with self.db.connect() as connection:
                material_link = connection.execute(
                    """SELECT source_revision,relation FROM assistant_wiki_materials
                    WHERE page_id=? AND video_id=?""",
                    (existing["id"], video_id),
                ).fetchone()
                duplicate_content = connection.execute(
                    """
                    SELECT 1 FROM assistant_wiki_dependencies d
                    JOIN assistant_source_cards old_card ON old_card.revision=d.source_revision
                    JOIN assistant_source_cards new_card ON new_card.revision=?
                    WHERE d.page_id=? AND d.video_id=?
                      AND old_card.input_hash=new_card.input_hash
                      AND d.source_revision<>? LIMIT 1
                    """,
                    (revision, existing["id"], video_id, revision),
                ).fetchone()
                old_revisions = [str(item["source_revision"]) for item in connection.execute(
                    """SELECT DISTINCT source_revision FROM assistant_wiki_dependencies
                    WHERE page_id=? AND video_id=? AND source_revision<>?""",
                    (existing["id"], video_id, revision),
                ).fetchall()]
            if duplicate_content is None and old_revisions:
                new_snapshot = self.sources._capture_or_load(video_id, revision).snapshot
                duplicate_content = next((old_revision for old_revision in old_revisions
                    if self._card_body_equivalent(
                        self.sources._capture_or_load(video_id, old_revision).snapshot,
                        new_snapshot, self.get_source_card(old_revision) or {},
                    )), None)
            if material_link is not None and str(material_link["source_revision"]) == revision and (
                str(material_link["relation"]) == "associated" or
                (current_existing and current_existing["availability"] == "full" and any(
                    revision in block.get("source_refs", []) and
                    block.get("compiler_version") == self.COMPILER_VERSION
                    for block in current_existing["blocks"]
                ))
            ):
                return {"no_change": True, "reason": "material_already_processed",
                        "page_id": existing["id"], "version": existing["version"]}
            if duplicate_content is not None:
                return self._rebind_equivalent_source(
                    existing, space=space, video_id=video_id, revision=revision,
                    job=job,
                )
        if existing and current_existing and current_existing["availability"] == "full" and any(
            revision in block.get("source_refs", []) and
            block.get("compiler_version") == self.COMPILER_VERSION
            for block in current_existing["blocks"]
        ):
            return {"no_change": True, "page_id": existing["id"], "version": existing["version"]}
        catalog_revisions = [revision]
        if existing is not None:
            catalog_revisions.extend(self._current_page_source_revisions(
                str(existing["id"]), space=space
            ))
        catalog_revisions = list(dict.fromkeys(catalog_revisions))[:6]
        source_key_map = {f"s{index + 1}": value for index, value in enumerate(catalog_revisions)}
        invalid_block_directory = [{
            "id": block["stable_id"], "heading": str(block["heading"])[:120],
            "current_source_keys": [key for key, value in source_key_map.items()
                                    if value in block.get("source_refs", [])],
        } for block in (existing or {}).get("blocks", [])
            if block["stable_id"] not in visible_block_ids and block.get("source_refs")]
        source_catalog = [{
            "key": key,
            "card": {
                field: value for field, value in (self.get_source_card(source_revision) or {}).items()
                if field in {"title", "uploader", "published_at", "coverage", "material_kind",
                             "summary", "key_points", "limitations"}
            },
        } for key, source_revision in source_key_map.items()]
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
                        "existing_page": self._page_for_prompt(current_existing, source_key_map=source_key_map),
                        "page_directory": [{"id": block["stable_id"], "heading": block["heading"][:100],
                                            "applicability": str(block.get("applicability") or "")[:160],
                                            "manual": bool(block.get("manual_lock")),
                                            "source_count": len(block.get("source_refs", []))}
                                           for block in (current_existing or {}).get("blocks", [])[:80]],
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
        if fuzzy_candidate and existing is not None and response.get("same_topic") is not True:
            existing = None
            source_key_map = {"s1": revision}
            if not payload.get("task_topic") and not payload.get("maintenance_batch_id"):
                return {"no_change": True, "reason": "no_existing_topic_match", "revision": revision}
        patch = self._normalize_wiki_patch(response, topic=topic, card=card, revision=revision,
                                           source_key_map=source_key_map,
                                           source_titles={item["key"]: str(item["card"].get("title") or "材料")
                                                          for item in source_catalog})
        local_operation = str(response.get("operation") or "") if existing is not None else ""
        if local_operation not in {"add_block", "revise_block", "associate", "no_change"}:
            local_operation = ""
        if payload.get("repair_page_id") and invalid_block_directory and (
            local_operation != "revise_block" or
            str(response.get("target_block_id") or "") not in
            {str(item["id"]) for item in invalid_block_directory}
        ):
            return {"no_change": True, "reason": "repair_requires_current_supported_revision",
                    "page_id": existing["id"], "version": existing["version"]}
        if local_operation == "no_change":
            return {"no_change": True, "reason": "no_new_topic_value", "revision": revision,
                    "page_id": existing["id"], "version": existing["version"]}
        if local_operation in {"add_block", "revise_block"}:
            patch["blocks"] = patch["blocks"][:1]
            if not patch["blocks"] or revision not in patch["blocks"][0].get("source_refs", []):
                return {"no_change": True, "reason": "proposal_missing_new_source_support", "revision": revision}
            patch["replace_derived"] = False
            patch["local_operation"] = local_operation
            patch["target_block_id"] = str(response.get("target_block_id") or "")
            # Preserve a currently valid guide; a partial page must not reuse
            # prose that may summarize a withdrawn source.
            if local_operation == "revise_block":
                patch["summary"] = self._pending_guide()
            elif current_existing and current_existing["availability"] == "full":
                prior_guide = str(current_existing.get("summary") or "")[:1800]
                patch["summary"] = (
                    prior_guide + f" 新增对照：{patch['blocks'][0]['heading']}；具体条件与出处见对应内容。"
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
            return {"no_change": True, "reason": "no_new_topic_value", "revision": revision,
                    **({"page_id": existing["id"], "version": existing["version"]} if existing else {})}
        if patch.get("replace_derived") and not local_operation:
            covered = {ref for block in patch["blocks"] for ref in block.get("source_refs", [])}
            if not set(catalog_revisions).issubset(covered):
                return {"no_change": True, "reason": "proposal_missing_source_coverage",
                        "revision": revision,
                        **({"page_id": existing["id"], "version": existing["version"]} if existing else {})}
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
            )
        except AssistantConflict as exc:
            if str(exc) == "proposal_missing_source_coverage":
                return {"no_change": True, "reason": str(exc), "revision": revision}
            if str(exc) in {
                "wiki_job_lease_lost", "wiki_job_payload_changed",
                "wiki_scope_changed", "wiki_source_out_of_scope",
                "source_revision_changed", "wiki_task_input_stale",
            }:
                return {"superseded": True, "reason": str(exc)}
            raise
        return {"page_id": page["id"], "version": page["version"], "title": page["title"]}

    def _rebind_equivalent_source(
        self, page: dict[str, Any], *, space: dict[str, Any], video_id: int,
        revision: str, job: dict[str, Any],
    ) -> dict[str, Any]:
        """Advance an equivalent card's provenance without another model call."""
        now = utc_now()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._validate_wiki_commit_fence(
                connection, space_id=int(space["id"]), video_id=video_id,
                revision=revision, scope_version=int(space["scope_version"]),
                job_id=str(job["id"]), lease_owner=str(job["lease_owner"]),
                lease_epoch=int(job["lease_epoch"]), now=now,
            )
            row = connection.execute(
                "SELECT * FROM assistant_wiki_pages WHERE id=? AND status='active'",
                (page["id"],),
            ).fetchone()
            if row is None or int(row["version"]) != int(page["version"]):
                raise AssistantConflict("wiki_version_conflict")
            before = self._decode_page(dict(row))
            before_state = self._operation_state(connection, str(page["id"]))
            old_rows = connection.execute(
                """SELECT DISTINCT d.source_revision,old_card.input_hash AS old_hash,
                       new_card.input_hash AS new_hash
                FROM assistant_wiki_dependencies d
                JOIN assistant_source_cards old_card ON old_card.revision=d.source_revision
                JOIN assistant_source_cards new_card ON new_card.revision=?
                WHERE d.page_id=? AND d.video_id=? AND d.source_revision<>?""",
                (revision, page["id"], video_id, revision),
            ).fetchall()
            new_snapshot = self.sources._capture_or_load(video_id, revision).snapshot
            old_revisions = {str(item["source_revision"]) for item in old_rows
                if item["old_hash"] == item["new_hash"] or self._card_body_equivalent(
                    self.sources._capture_or_load(video_id, str(item["source_revision"])).snapshot,
                    new_snapshot, self.get_source_card(str(item["source_revision"])) or {},
                )}
            if not old_revisions:
                return {"no_change": True, "reason": "equivalent_source_already_current",
                        "page_id": page["id"], "version": page["version"]}
            blocks = []
            for block in before["blocks"]:
                item = dict(block)
                item["source_refs"] = list(dict.fromkeys(
                    revision if ref in old_revisions else ref
                    for ref in item.get("source_refs", [])
                ))
                blocks.append(item)
            for old_revision in old_revisions:
                connection.execute(
                    """INSERT OR IGNORE INTO assistant_wiki_dependencies(
                        page_id,block_id,source_revision,video_id,dependency_kind,created_at
                    ) SELECT page_id,block_id,?,video_id,dependency_kind,?
                      FROM assistant_wiki_dependencies
                      WHERE page_id=? AND video_id=? AND source_revision=?""",
                    (revision, now, page["id"], video_id, old_revision),
                )
                connection.execute(
                    "DELETE FROM assistant_wiki_dependencies WHERE page_id=? AND video_id=? AND source_revision=?",
                    (page["id"], video_id, old_revision),
                )
            version = int(before["version"]) + 1
            connection.execute(
                "UPDATE assistant_wiki_pages SET blocks_json=?, version=?, scope_version=?, updated_at=? WHERE id=?",
                (json.dumps(blocks, ensure_ascii=False), version, int(space["scope_version"]), now, page["id"]),
            )
            connection.execute(
                """UPDATE assistant_wiki_materials SET source_revision=?, updated_at=?
                WHERE page_id=? AND video_id=?""",
                (revision, now, page["id"], video_id),
            )
            after = self._decode_page(dict(connection.execute(
                "SELECT * FROM assistant_wiki_pages WHERE id=?", (page["id"],)
            ).fetchone()))
            connection.execute(
                """INSERT INTO assistant_wiki_changes(
                    page_id,version,operation,before_json,after_json,summary,actor,created_at
                ) VALUES(?,?,'source_rebound',?,?,?,'assistant',?)""",
                (page["id"], version, json.dumps(before, ensure_ascii=False),
                 json.dumps(after, ensure_ascii=False), "等价材料的来源版本已更新", now),
            )
            self._fts_replace(connection, after)
            self._save_operation_state(connection, str(page["id"]), version, before_state)
        return {"page_id": page["id"], "version": version,
                "no_model_call": True, "reason": "equivalent_source_rebound"}

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
    ) -> dict[str, Any]:
        now = utc_now()
        normalized = self._normalize_title(str(patch["title"]))
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
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
            )
            space_row = connection.execute(
                "SELECT source_ids_json,video_ids_json,all_active FROM assistant_spaces WHERE id=?",
                (space_id,),
            ).fetchone()
            selected_videos = {int(value) for value in json.loads(space_row["video_ids_json"] or "[]")}
            selected_sources = {int(value) for value in json.loads(space_row["source_ids_json"] or "[]")}
            row = connection.execute(
                """
                SELECT * FROM assistant_wiki_pages
                WHERE principal_id=? AND space_id=? AND normalized_title=? AND status='active'
                """,
                (self.principal_id, space_id, normalized),
            ).fetchone()
            before_state = self._operation_state(connection, str(row["id"])) if row else None
            if row is None:
                if expected_version != 0:
                    raise AssistantConflict("wiki_page_missing")
                page_id = f"awiki_{uuid.uuid4().hex}"
                blocks = self._blocks_with_identity(patch["blocks"], revision=revision, topic=patch["title"])
                incoming_ids = {block["stable_id"] for block in blocks}
                connection.execute(
                    """
                    INSERT INTO assistant_wiki_pages(
                        id, principal_id, space_id, normalized_title, title, aliases_json,
                        page_type, summary, blocks_json, version, status, scope_version,
                        created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'active', ?, ?, ?)
                    """,
                    (
                        page_id, self.principal_id, space_id, normalized, patch["title"],
                        json.dumps(patch.get("aliases", []), ensure_ascii=False),
                        patch["page_type"], patch["summary"],
                        json.dumps(blocks, ensure_ascii=False), scope_version, now, now,
                    ),
                )
                version = 1
                before = None
                operation = "created"
            else:
                current = self._decode_page(dict(row))
                if int(current["version"]) != expected_version:
                    raise AssistantConflict("wiki_version_conflict")
                page_id = str(current["id"])
                blocks = list(current["blocks"])
                local_operation = str(patch.get("local_operation") or "")
                target_id = str(patch.get("target_block_id") or "")
                if local_operation == "revise_block":
                    target = next((item for item in blocks if item["stable_id"] == target_id), None)
                    if target is None or target.get("manual_lock"):
                        raise AssistantConflict("wiki_manual_conflict")
                    incoming_refs = {str(ref) for item in patch["blocks"]
                                     for ref in item.get("source_refs", [])}
                    valid_refs = set(self._current_page_source_revisions(page_id, space=self.store.get_space(space_id)))
                    if not set(target.get("source_refs", [])).intersection(valid_refs).issubset(incoming_refs):
                        raise AssistantConflict("proposal_missing_source_coverage")
                if patch.get("replace_derived"):
                    covered = {str(ref) for block in patch["blocks"]
                               for ref in block.get("source_refs", [])}
                    active_refs = {
                        str(item["source_revision"])
                        for item in connection.execute(
                            """SELECT DISTINCT d.source_revision, d.video_id, m.source_id
                            FROM assistant_wiki_dependencies d
                            JOIN assistant_source_heads h ON h.video_id=d.video_id
                              AND h.principal_id=? AND h.current_revision=d.source_revision
                            JOIN video_source_memberships m ON m.video_id=d.video_id AND m.removed_at IS NULL
                            JOIN favorite_sources s ON s.id=m.source_id AND s.status='active'
                            JOIN videos v ON v.id=d.video_id AND v.is_ignored=0 AND v.archived_at IS NULL
                            WHERE d.page_id=?""", (self.principal_id, page_id)
                        ).fetchall()
                        if (not selected_videos or int(item["video_id"]) in selected_videos)
                        and (bool(space_row["all_active"]) or int(item["source_id"]) in selected_sources)
                    }
                    if not active_refs.issubset(covered) or revision not in covered:
                        raise AssistantConflict("proposal_missing_source_coverage")
                prior_ids = {
                    str(item["block_id"])
                    for item in connection.execute(
                        """
                        SELECT block_id FROM assistant_wiki_dependencies
                        WHERE page_id=? AND video_id=? AND source_revision<>?
                        """,
                        (page_id, video_id, revision),
                    ).fetchall()
                }
                replace_ids = {
                    block["stable_id"] for block in blocks
                    if not block.get("manual_lock") and (
                        (local_operation == "revise_block" and block["stable_id"] == target_id) or
                        (not local_operation and bool(patch.get("replace_derived"))) or
                        (not local_operation and block["stable_id"] in prior_ids) or
                        (not local_operation and revision in block.get("source_refs", []) and
                         block.get("compiler_version") != self.COMPILER_VERSION)
                    )
                }
                if replace_ids:
                    blocks = [block for block in blocks if block["stable_id"] not in replace_ids]
                    placeholders = ",".join("?" for _ in replace_ids)
                    connection.execute(
                        f"DELETE FROM assistant_wiki_dependencies WHERE page_id=? "
                        f"AND block_id IN ({placeholders})",
                        (page_id, *sorted(replace_ids)),
                    )
                incoming = self._blocks_with_identity(patch["blocks"], revision=revision, topic=patch["title"])
                incoming_ids = {block["stable_id"] for block in incoming}
                blocks.extend(block for block in incoming if block["stable_id"] not in {b["stable_id"] for b in blocks})
                if local_operation in {"add_block", "revise_block"}:
                    retained = {str(ref) for block in blocks for ref in block.get("source_refs", [])}
                    active_refs = set(self._current_page_source_revisions(page_id, space=self.store.get_space(space_id)))
                    if not active_refs.issubset(retained) or revision not in retained:
                        raise AssistantConflict("proposal_missing_source_coverage")
                version = expected_version + 1
                before = current
                operation = "source_amended" if replace_ids else (
                    "source_associated" if local_operation == "associate" else "source_integrated"
                )
                aliases = list(dict.fromkeys([
                    *current["aliases"],
                    *[str(value) for value in patch.get("aliases", []) if str(value).strip()],
                ]))[:24]
                updated = connection.execute(
                    """
                    UPDATE assistant_wiki_pages SET summary=?, blocks_json=?, aliases_json=?, page_type=?,
                        version=?, scope_version=?, status='active', updated_at=?
                    WHERE id=? AND version=?
                    """,
                    (
                        str(patch.get("summary") or current["summary"]),
                        json.dumps(blocks, ensure_ascii=False),
                        json.dumps(aliases, ensure_ascii=False), patch["page_type"], version,
                        scope_version, now, page_id, expected_version,
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
                        WHERE r.revision=? AND h.principal_id=? AND h.current_revision=?""",
                        (block_revision, self.principal_id, block_revision),
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
                        WHERE m.video_id=? AND m.removed_at IS NULL AND s.status='active'
                          AND v.is_ignored=0 AND v.archived_at IS NULL""",
                        (source_video_id,),
                    ).fetchall()
                    if not any(bool(space_row["all_active"]) or int(row["source_id"]) in selected_sources
                               for row in memberships):
                        raise AssistantConflict("wiki_source_out_of_scope")
                    connection.execute(
                        """INSERT OR IGNORE INTO assistant_wiki_dependencies(
                            page_id, block_id, source_revision, video_id, dependency_kind, created_at
                        ) VALUES(?, ?, ?, ?, 'source', ?)""",
                        (page_id, block["stable_id"], block_revision, source_video_id, now),
                    )
            relation = "associated" if patch.get("local_operation") == "associate" else "supports_block"
            connection.execute(
                """INSERT INTO assistant_wiki_materials(
                    page_id,video_id,source_revision,relation,status,created_at,updated_at
                ) VALUES(?,?,?,?,'integrated',?,?)
                ON CONFLICT(page_id,video_id) DO UPDATE SET
                    source_revision=excluded.source_revision, relation=excluded.relation,
                    status=excluded.status, updated_at=excluded.updated_at""",
                (page_id, video_id, revision, relation, now, now),
            )
            for block in blocks:
                for block_revision in block.get("source_refs", []):
                    source = connection.execute(
                        "SELECT video_id FROM assistant_source_cards WHERE revision=?",
                        (block_revision,),
                    ).fetchone()
                    if source:
                        connection.execute(
                            """INSERT OR IGNORE INTO assistant_wiki_materials(
                                page_id,video_id,source_revision,relation,status,created_at,updated_at
                            ) VALUES(?,?,?,'supports_block','integrated',?,?)""",
                            (page_id, int(source["video_id"]), block_revision, now, now),
                        )
            after_row = connection.execute(
                "SELECT * FROM assistant_wiki_pages WHERE id=?", (page_id,)
            ).fetchone()
            after = self._decode_page(dict(after_row))
            connection.execute(
                """
                INSERT INTO assistant_wiki_changes(
                    page_id, version, operation, before_json, after_json, summary, actor, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, 'assistant', ?)
                """,
                (
                    page_id, version, operation,
                    json.dumps(before, ensure_ascii=False) if before else None,
                    json.dumps(after, ensure_ascii=False),
                    f"纳入来源：{patch.get('source_title') or revision[:8]}", now,
                ),
            )
            self._fts_replace(connection, after)
            self._save_operation_state(connection, page_id, version, before_state)
        return self.get_page(page_id, space_id=space_id, include_hidden=True)

    def _operation_state(self, connection: Any, page_id: str) -> dict[str, Any]:
        row = connection.execute("SELECT * FROM assistant_wiki_pages WHERE id=?", (page_id,)).fetchone()
        if row is None:
            raise KeyError(page_id)
        return {
            "page": self._decode_page(dict(row)),
            "sources": [dict(item) for item in connection.execute(
                """SELECT block_id,source_revision,video_id,dependency_kind
                FROM assistant_wiki_dependencies WHERE page_id=?""", (page_id,)
            ).fetchall()],
            "personal": [dict(item) for item in connection.execute(
                """SELECT block_id,memory_id,memory_version,source_message_id
                FROM assistant_wiki_personal_dependencies WHERE page_id=?""", (page_id,)
            ).fetchall()],
            "materials": [dict(item) for item in connection.execute(
                """SELECT video_id,source_revision,relation,status
                FROM assistant_wiki_materials WHERE page_id=?""", (page_id,)
            ).fetchall()],
            "redirects": [dict(item) for item in connection.execute(
                "SELECT old_page_id FROM assistant_wiki_redirects WHERE target_page_id=?",
                (page_id,),
            ).fetchall()],
        }

    def _save_operation_state(
        self, connection: Any, page_id: str, version: int,
        before: dict[str, Any] | None,
    ) -> None:
        after = self._operation_state(connection, page_id)
        connection.execute(
            """INSERT INTO assistant_wiki_operation_states(page_id,version,before_json,after_json)
            VALUES(?,?,?,?)""",
            (page_id, version, json.dumps(before, ensure_ascii=False) if before else None,
             json.dumps(after, ensure_ascii=False)),
        )

    def history_source_refs(self, page_id: str, *, space_id: int) -> list[str]:
        page = self.get_page(page_id, space_id=space_id)
        visible_blocks = {str(block["stable_id"]) for block in page["blocks"]}
        if not visible_blocks:
            return []
        placeholders = ",".join("?" for _ in visible_blocks)
        with self.db.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT d.video_id, d.source_revision
                FROM assistant_wiki_dependencies d
                JOIN assistant_source_heads h ON h.video_id=d.video_id
                    AND h.principal_id=? AND h.current_revision=d.source_revision
                WHERE d.page_id=? AND d.block_id IN ({placeholders})
                """,
                (self.principal_id, page_id, *sorted(visible_blocks)),
            ).fetchall()
        refs: list[str] = []
        for row in rows:
            refs.append(f"video:{int(row['video_id'])}:{row['source_revision']}")
        if any(block.get("source_refs") for block in page["blocks"]) and not refs:
            raise ValueError("historical_result_dependencies_missing")
        return sorted(set(refs))

    def _current_page_source_revisions(
        self, page_id: str, *, space: dict[str, Any]
    ) -> list[str]:
        """Find current cards even when a mixed old/new block must be hidden."""
        visible_video_ids = set(self.sources.visible_video_ids(self._scope(space)))
        with self.db.connect() as connection:
            rows = connection.execute(
                """SELECT DISTINCT d.video_id, d.source_revision
                FROM assistant_wiki_dependencies d
                JOIN assistant_source_heads h ON h.video_id=d.video_id
                  AND h.principal_id=? AND h.current_revision=d.source_revision
                WHERE d.page_id=? ORDER BY d.video_id, d.source_revision""",
                (self.principal_id, page_id),
            ).fetchall()
        return [str(row["source_revision"]) for row in rows
                if int(row["video_id"]) in visible_video_ids]

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
    ) -> None:
        job = connection.execute(
            """
            SELECT kind, status, payload_json, lease_owner, lease_until, lease_epoch
            FROM assistant_jobs WHERE id=?
            """,
            (job_id,),
        ).fetchone()
        if (
            job is None
            or str(job["kind"]) != "wiki_integrate"
            or str(job["status"]) != "running"
            or str(job["lease_owner"] or "") != lease_owner
            or int(job["lease_epoch"]) != lease_epoch
            or not job["lease_until"]
            or str(job["lease_until"]) < now
        ):
            raise AssistantConflict("wiki_job_lease_lost")
        job_payload = json.loads(job["payload_json"] or "{}")
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
                WHERE m.id=? AND m.role='user' AND t.space_id=? AND t.principal_id=?""",
                (source_message_id, space_id, self.principal_id),
            ).fetchone()
            if source_message is None:
                raise AssistantConflict("wiki_task_input_stale")
            suppressed = connection.execute(
                """SELECT source_message_ids_json FROM assistant_memory_suppressions
                WHERE principal_id=? AND (scope_kind='user' OR (scope_kind='space' AND scope_id=?))""",
                (self.principal_id, str(space_id)),
            ).fetchall()
            if any(source_message_id in json.loads(row["source_message_ids_json"] or "[]")
                   for row in suppressed):
                raise AssistantConflict("wiki_task_input_stale")
        space = connection.execute(
            """
            SELECT source_ids_json, video_ids_json, all_active, scope_version, enabled
            FROM assistant_spaces WHERE id=? AND principal_id=?
            """,
            (space_id, self.principal_id),
        ).fetchone()
        if (
            space is None
            or not bool(space["enabled"])
            or int(space["scope_version"]) != scope_version
        ):
            raise AssistantConflict("wiki_scope_changed")
        selected_sources = {
            int(value) for value in json.loads(space["source_ids_json"] or "[]")
        }
        selected_videos = {
            int(value) for value in json.loads(space["video_ids_json"] or "[]")
        }
        if selected_videos and video_id not in selected_videos:
            raise AssistantConflict("wiki_source_out_of_scope")
        membership_params: list[Any] = [video_id]
        source_clause = ""
        if not bool(space["all_active"]):
            if not selected_sources:
                raise AssistantConflict("wiki_source_out_of_scope")
            placeholders = ",".join("?" for _ in selected_sources)
            source_clause = f" AND m.source_id IN ({placeholders})"
            membership_params.extend(sorted(selected_sources))
        visible = connection.execute(
            f"""
            SELECT 1 FROM video_source_memberships m
            JOIN favorite_sources s ON s.id=m.source_id
            JOIN videos v ON v.id=m.video_id
            WHERE m.video_id=? AND m.removed_at IS NULL AND s.status='active'
              AND v.is_ignored=0 AND v.archived_at IS NULL {source_clause}
            LIMIT 1
            """,
            membership_params,
        ).fetchone()
        if visible is None:
            raise AssistantConflict("wiki_source_out_of_scope")
        head = connection.execute(
            """
            SELECT current_revision FROM assistant_source_heads
            WHERE principal_id=? AND video_id=?
            """,
            (self.principal_id, video_id),
        ).fetchone()
        if head is None or str(head["current_revision"] or "") != revision:
            raise AssistantConflict("source_revision_changed")

    def list_pages(self, *, space_id: int, query: str = "") -> list[dict[str, Any]]:
        self.store.get_space(space_id)
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM assistant_wiki_pages
                WHERE principal_id=? AND space_id=? AND status='active'
                ORDER BY updated_at DESC, title
                """,
                (self.principal_id, space_id),
            ).fetchall()
        query_tokens = self._topic_tokens(query) if query.strip() else set()
        values: list[tuple[int, dict[str, Any]]] = []
        for row in rows:
            page = self._visible_page(self._decode_page(dict(row)))
            if not page["blocks"]:
                continue
            if query_tokens:
                searchable = " ".join([
                    page["title"], page["summary"],
                    *[f"{block['heading']} {block['markdown']}" for block in page["blocks"]],
                ])
                score = len(query_tokens.intersection(self._topic_tokens(searchable)))
                if score == 0:
                    continue
            else:
                score = 0
            values.append((score, page))
        values.sort(key=lambda item: (item[0], item[1]["updated_at"]), reverse=True)
        return [page for _score, page in values]

    def get_page(
        self, page_id: str, *, space_id: int | None = None, include_hidden: bool = False
    ) -> dict[str, Any]:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM assistant_wiki_pages WHERE id=? AND principal_id=?",
                (page_id, self.principal_id),
            ).fetchone()
            redirect = connection.execute(
                "SELECT target_page_id,space_id FROM assistant_wiki_redirects WHERE old_page_id=?",
                (page_id,),
            ).fetchone()
        if row is None:
            raise KeyError(page_id)
        page = self._decode_page(dict(row))
        if space_id is not None and int(page["space_id"]) != int(space_id):
            raise KeyError(page_id)
        if page["status"] == "merged" and redirect is not None:
            if int(redirect["space_id"]) != int(page["space_id"]):
                raise KeyError(page_id)
            target = self.get_page(str(redirect["target_page_id"]), space_id=int(page["space_id"]))
            return {**target, "redirected_from": page_id}
        if page["status"] != "active" and not include_hidden:
            raise KeyError(page_id)
        return page if include_hidden else self._visible_page(page)

    def edit_block(
        self,
        page_id: str,
        *,
        block_id: str,
        markdown: str,
        expected_version: int,
        operation_key: str,
    ) -> dict[str, Any]:
        clean = markdown.strip()
        if not clean or len(clean) > 20000:
            raise ValueError("invalid_wiki_block")
        now = utc_now()
        with self.db.connect() as connection:
            receipt = connection.execute(
                "SELECT result_json FROM assistant_mutation_receipts WHERE operation_key=? AND principal_id=?",
                (operation_key, self.principal_id),
            ).fetchone()
            if receipt is not None:
                return json.loads(receipt["result_json"])
            row = connection.execute(
                "SELECT * FROM assistant_wiki_pages WHERE id=? AND principal_id=?",
                (page_id, self.principal_id),
            ).fetchone()
            if row is None:
                raise KeyError(page_id)
            before = self._decode_page(dict(row))
            before_state = self._operation_state(connection, page_id)
            if int(before["version"]) != expected_version:
                raise AssistantConflict("wiki_version_conflict")
            blocks = list(before["blocks"])
            target = next((block for block in blocks if block["stable_id"] == block_id), None)
            if target is None:
                raise KeyError(block_id)
            target["markdown"] = clean
            target["manual_lock"] = True
            version = expected_version + 1
            updated = connection.execute(
                """
                UPDATE assistant_wiki_pages SET blocks_json=?, summary=?, version=?, updated_at=?
                WHERE id=? AND version=?
                """,
                (json.dumps(blocks, ensure_ascii=False), self._pending_guide(),
                 version, now, page_id, expected_version),
            )
            if updated.rowcount != 1:
                raise AssistantConflict("wiki_version_conflict")
            after = self._decode_page(dict(connection.execute(
                "SELECT * FROM assistant_wiki_pages WHERE id=?", (page_id,)
            ).fetchone()))
            connection.execute(
                """
                INSERT INTO assistant_wiki_changes(
                    page_id, version, operation, before_json, after_json, summary, actor, created_at
                ) VALUES(?, ?, 'block_edited', ?, ?, '人工编辑知识块', 'user', ?)
                """,
                (page_id, version, json.dumps(before, ensure_ascii=False), json.dumps(after, ensure_ascii=False), now),
            )
            self._fts_replace(connection, after)
            self._save_operation_state(connection, page_id, version, before_state)
            connection.execute(
                """
                INSERT INTO assistant_mutation_receipts(
                    operation_key, principal_id, operation, result_json, created_at
                ) VALUES(?, ?, 'wiki_edit', ?, ?)
                """,
                (operation_key, self.principal_id, json.dumps(after, ensure_ascii=False), now),
            )
        return self._visible_page(after)

    def revise_derived_blocks(
        self, page_id: str, *, space_id: int, expected_version: int,
        edits: list[dict[str, str]], summary: str, operation_key: str,
    ) -> dict[str, Any]:
        """Traceable, bounded repair of selected generated blocks; never edit manual notes."""
        if not 1 <= len(edits) <= 4 or not 1 <= len(summary) <= 3000:
            raise ValueError("invalid_derived_revision")
        now = utc_now()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            receipt = connection.execute(
                "SELECT result_json FROM assistant_mutation_receipts WHERE operation_key=? AND principal_id=?",
                (operation_key, self.principal_id),
            ).fetchone()
            if receipt:
                return self._visible_page(json.loads(receipt["result_json"]))
            row = connection.execute(
                """SELECT * FROM assistant_wiki_pages WHERE id=? AND principal_id=? AND space_id=?
                AND status='active'""", (page_id, self.principal_id, space_id),
            ).fetchone()
            if row is None:
                raise KeyError(page_id)
            before = self._decode_page(dict(row))
            if int(before["version"]) != expected_version:
                raise AssistantConflict("wiki_version_conflict")
            before_state = self._operation_state(connection, page_id)
            blocks = list(before["blocks"])
            seen = set()
            source_replacements: list[tuple[str, list[tuple[int, str]]]] = []
            for edit in edits:
                block_id = edit.get("block_id")
                if block_id in seen:
                    raise ValueError("duplicate_block_edit")
                seen.add(block_id)
                target = next((item for item in blocks if item["stable_id"] == block_id), None)
                discussion_role_fix = bool(target and target.get("user_input_source") == "discussion"
                                           and edit.get("assessment") == "system_synthesis")
                if target is None or ((target.get("manual_lock") or target.get("assessment") == "user_explicit")
                                      and not discussion_role_fix):
                    raise AssistantConflict("wiki_manual_conflict")
                heading, body = str(edit.get("heading") or "").strip(), str(edit.get("markdown") or "").strip()
                if not heading or not body or len(heading) > 160 or len(body) > 12000:
                    raise ValueError("invalid_derived_revision")
                target["heading"], target["markdown"] = heading, body
                if "applicability" in edit:
                    target["applicability"] = str(edit["applicability"]).strip()[:600]
                if "assessment" in edit:
                    if edit["assessment"] not in {"source_reported", "system_synthesis"}:
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
                        if len(parts) != 3 or parts[0] != "video" or not parts[1].isdigit():
                            raise ValueError("versioned_video_source_required")
                        video_id, revision = int(parts[1]), parts[2]
                        head = connection.execute(
                            "SELECT current_revision FROM assistant_source_heads WHERE principal_id=? AND video_id=?",
                            (self.principal_id, video_id),
                        ).fetchone()
                        if head is None or str(head["current_revision"]) != revision:
                            raise AssistantConflict("source_revision_changed")
                        if video_id not in self.sources.visible_video_ids(self._scope(self.store.get_space(space_id))):
                            raise AssistantConflict("wiki_source_out_of_scope")
                        resolved.append((video_id, revision))
                    target["source_refs"] = [revision for _, revision in resolved]
                    source_replacements.append((block_id, resolved))
            for block_id, resolved in source_replacements:
                connection.execute(
                    "DELETE FROM assistant_wiki_dependencies WHERE page_id=? AND block_id=?",
                    (page_id, block_id),
                )
                for video_id, revision in resolved:
                    connection.execute(
                        """INSERT INTO assistant_wiki_dependencies(page_id,block_id,source_revision,video_id,
                        dependency_kind,created_at) VALUES(?,?,?,?,'source',?)""",
                        (page_id, block_id, revision, video_id, now),
                    )
            if source_replacements:
                connection.execute(
                    """UPDATE assistant_wiki_materials SET relation='associated',updated_at=?
                    WHERE page_id=? AND video_id NOT IN
                    (SELECT DISTINCT video_id FROM assistant_wiki_dependencies WHERE page_id=?)""",
                    (now, page_id, page_id),
                )
            version = expected_version + 1
            connection.execute(
                """UPDATE assistant_wiki_pages SET summary=?,blocks_json=?,version=?,updated_at=?
                WHERE id=? AND version=?""",
                (summary, json.dumps(blocks, ensure_ascii=False), version, now, page_id, expected_version),
            )
            after = self._decode_page(dict(connection.execute(
                "SELECT * FROM assistant_wiki_pages WHERE id=?", (page_id,)
            ).fetchone()))
            connection.execute(
                """INSERT INTO assistant_wiki_changes(page_id,version,operation,before_json,after_json,
                summary,actor,created_at) VALUES(?,?,'derived_repair',?,?,?,'assistant',?)""",
                (page_id, version, json.dumps(before, ensure_ascii=False), json.dumps(after, ensure_ascii=False),
                 "定点修正生成内容", now),
            )
            self._fts_replace(connection, after)
            self._save_operation_state(connection, page_id, version, before_state)
            connection.execute(
                """INSERT INTO assistant_mutation_receipts(operation_key,principal_id,operation,result_json,created_at)
                VALUES(?,?,'wiki_derived_repair',?,?)""",
                (operation_key, self.principal_id, json.dumps(after, ensure_ascii=False), now),
            )
        return self._visible_page(after)

    def add_personal_note(
        self, page_id: str, *, space_id: int, text: str,
        expected_version: int, operation_key: str,
        memory_id: str | None = None, memory_version: int | None = None,
        source_message_id: str | None = None,
    ) -> dict[str, Any]:
        clean = text.strip()
        if not clean or len(clean) > 4000:
            raise ValueError("invalid_personal_note")
        now = utc_now()
        if bool(memory_id) != (memory_version is not None):
            raise ValueError("memory_dependency_required")
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            receipt = connection.execute(
                "SELECT result_json FROM assistant_mutation_receipts WHERE operation_key=? AND principal_id=?",
                (operation_key, self.principal_id),
            ).fetchone()
            if receipt is not None:
                return self._visible_page(json.loads(receipt["result_json"]))
            row = connection.execute(
                "SELECT * FROM assistant_wiki_pages WHERE id=? AND principal_id=? AND space_id=? AND status='active'",
                (page_id, self.principal_id, space_id),
            ).fetchone()
            if row is None:
                raise KeyError(page_id)
            before = self._decode_page(dict(row))
            before_state = self._operation_state(connection, page_id)
            if int(before["version"]) != expected_version:
                raise AssistantConflict("wiki_version_conflict")
            if memory_id and not self._personal_dependency_current(
                connection, space_id=space_id, memory_id=memory_id,
                memory_version=int(memory_version), source_message_id=source_message_id,
            ):
                raise AssistantConflict("personal_dependency_stale")
            source_time = now
            source_text = ""
            if source_message_id:
                source_message = connection.execute(
                    """SELECT m.content,m.created_at FROM assistant_messages m JOIN assistant_threads t ON t.id=m.thread_id
                    WHERE m.id=? AND m.role='user' AND t.principal_id=? AND t.space_id=?""",
                    (source_message_id, self.principal_id, space_id),
                ).fetchone()
                if source_message is None:
                    raise ValueError("user_source_required")
                source_time = str(source_message["created_at"])
                source_text = str(source_message["content"])
            if source_message_id and not memory_id and clean not in source_text:
                raise ValueError("personal_quote_required")
            if memory_id and source_message_id and clean not in source_text:
                memory = connection.execute(
                    "SELECT text FROM assistant_memories WHERE id=? AND principal_id=?",
                    (memory_id, self.principal_id),
                ).fetchone()
                if memory is None or clean not in str(memory["text"]):
                    raise ValueError("personal_quote_required")
            block_id = f"wblock_user_{uuid.uuid4().hex[:20]}"
            historical = bool(re.search(r"当时|那时|曾经|之前|过去", clean))
            validity = None if historical else anchored_validity(clean, source_time)
            uncertain_time = validity is None and has_time_reference(clean)
            blocks = [*before["blocks"], {
                "stable_id": block_id,
                "heading": "我的笔记", "markdown": clean,
                "source_refs": [], "applicability": "", "assessment": "user_explicit",
                "relation": "personal_note", "manual_lock": True,
                "user_input_source": "memory_derived" if memory_id else
                                     ("discussion" if source_message_id else "direct_ui"),
                "created_at": now, "source_message_id": source_message_id,
                **({"historical_statement": True,
                    "validity_note": "原话包含未能可靠解释的时间；仅作历史记录，当前安排需核对"}
                   if uncertain_time else ({"historical_statement": True} if historical else {})),
                **(validity or {}),
            }]
            version = expected_version + 1
            changed = connection.execute(
                "UPDATE assistant_wiki_pages SET blocks_json=?, version=?, updated_at=? WHERE id=? AND version=?",
                (json.dumps(blocks, ensure_ascii=False), version, now, page_id, expected_version),
            )
            if changed.rowcount != 1:
                raise AssistantConflict("wiki_version_conflict")
            if memory_id:
                connection.execute(
                    """INSERT INTO assistant_wiki_personal_dependencies(
                        page_id,block_id,memory_id,memory_version,source_message_id,created_at
                    ) VALUES(?,?,?,?,?,?)""",
                    (page_id, block_id, memory_id, int(memory_version), source_message_id, now),
                )
            after = self._decode_page(dict(connection.execute(
                "SELECT * FROM assistant_wiki_pages WHERE id=?", (page_id,),
            ).fetchone()))
            connection.execute(
                """INSERT INTO assistant_wiki_changes(
                    page_id,version,operation,before_json,after_json,summary,actor,created_at
                ) VALUES(?,?,'personal_note_added',?,?,'添加个人笔记','user',?)""",
                (page_id, version, json.dumps(before, ensure_ascii=False),
                 json.dumps(after, ensure_ascii=False), now),
            )
            self._fts_replace(connection, after)
            self._save_operation_state(connection, page_id, version, before_state)
            connection.execute(
                """INSERT INTO assistant_mutation_receipts(
                    operation_key,principal_id,operation,result_json,created_at
                ) VALUES(?,?,'wiki_personal_note',?,?)""",
                (operation_key, self.principal_id, json.dumps(after, ensure_ascii=False), now),
            )
        return self._visible_page(after)

    def save_discussion(
        self, *, space_id: int, title: str, purpose: str, blocks: list[dict[str, Any]],
        operation_key: str, expected_version: int | None = None,
        source_message_id: str | None = None,
        authorized_plan_id: str | None = None, authorized_plan_version: int | None = None,
    ) -> dict[str, Any]:
        """Save selected conclusions, with each block's role and current dependencies."""
        title, purpose = title.strip(), purpose.strip()
        if not title or len(title) > 120 or not purpose or len(purpose) > 600 or not 1 <= len(blocks) <= 8:
            raise ValueError("invalid_knowledge_save")
        space = self.store.get_space(space_id)
        if source_message_id is None:
            raise ValueError("user_source_required")
        now = utc_now()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            receipt = connection.execute(
                "SELECT result_json FROM assistant_mutation_receipts WHERE operation_key=? AND principal_id=?",
                (operation_key, self.principal_id),
            ).fetchone()
            if receipt:
                return self._visible_page(json.loads(receipt["result_json"]))
            message = connection.execute(
                """SELECT m.id,m.content,m.created_at,t.id AS thread_id FROM assistant_messages m
                JOIN assistant_threads t ON t.id=m.thread_id
                WHERE m.id=? AND m.role='user' AND t.principal_id=? AND t.space_id=?""",
                (source_message_id, self.principal_id, space_id),
            ).fetchone()
            if message is None:
                raise ValueError("user_source_required")
            current_space = connection.execute(
                "SELECT scope_version FROM assistant_spaces WHERE id=?", (space_id,)
            ).fetchone()
            if int(current_space["scope_version"]) != int(space["scope_version"]):
                raise AssistantConflict("wiki_scope_changed")
            if authorized_plan_id is not None:
                authorization = connection.execute(
                    """SELECT version,scope_version,status FROM assistant_knowledge_plans
                    WHERE id=? AND principal_id=? AND space_id=?""",
                    (authorized_plan_id, self.principal_id, space_id),
                ).fetchone()
                if (authorization is None or authorized_plan_version is None or
                        int(authorization["version"]) != authorized_plan_version or
                        int(authorization["scope_version"]) != int(current_space["scope_version"]) or
                        authorization["status"] != "partial"):
                    raise AssistantConflict("knowledge_plan_authorization_changed")
            normalized = self._normalize_title(title)
            row = connection.execute(
                """SELECT * FROM assistant_wiki_pages WHERE principal_id=? AND space_id=?
                AND normalized_title=? AND status='active'""",
                (self.principal_id, space_id, normalized),
            ).fetchone()
            before = self._decode_page(dict(row)) if row else None
            if before and expected_version != int(before["version"]):
                raise AssistantConflict("wiki_version_conflict")
            if not before and expected_version is not None:
                raise AssistantConflict("wiki_page_missing")
            page_id = str(before["id"]) if before else f"awiki_{uuid.uuid4().hex}"
            old_blocks = list(before["blocks"]) if before else []
            before_state = self._operation_state(connection, page_id) if before else None
            incoming = []
            source_links = []
            personal_links = []
            for item in blocks:
                role = str(item.get("role") or "")
                heading = str(item.get("heading") or "").strip()
                body = str(item.get("markdown") or "").strip()
                refs = list(dict.fromkeys(item.get("source_refs") or []))
                external = item.get("external_sources") or []
                if role not in {"source", "analysis", "personal"} or not heading or not body or len(body) > 12000:
                    raise ValueError("invalid_knowledge_block")
                if role == "source" and not refs and not external:
                    raise ValueError("source_block_requires_source")
                if role == "personal" and (refs or external):
                    raise ValueError("personal_block_source_conflict")
                if role == "personal":
                    quote = str(item.get("user_quote") or "").strip()
                    if (len(quote) < 4 or quote not in str(message["content"])
                            or " ".join(body.split()) != " ".join(quote.split())):
                        raise ValueError("personal_quote_required")
                memory_id, memory_version = item.get("memory_id"), item.get("memory_version")
                if bool(memory_id) != (memory_version is not None) or (memory_id and role == "source"):
                    raise ValueError("invalid_memory_dependency")
                block_id = f"wblock_{uuid.uuid4().hex[:20]}"
                revisions = []
                for ref in refs:
                    parts = str(ref).split(":")
                    if len(parts) != 3 or parts[0] != "video" or not parts[1].isdigit():
                        raise ValueError("versioned_video_source_required")
                    video_id, revision = int(parts[1]), parts[2]
                    head = connection.execute(
                        "SELECT current_revision FROM assistant_source_heads WHERE principal_id=? AND video_id=?",
                        (self.principal_id, video_id),
                    ).fetchone()
                    if head is None or str(head["current_revision"]) != revision:
                        raise AssistantConflict("source_revision_changed")
                    if video_id not in self.sources.visible_video_ids(self._scope(space)):
                        raise AssistantConflict("wiki_source_out_of_scope")
                    revisions.append(revision)
                    source_links.append((block_id, video_id, revision))
                external_links = []
                for source in external:
                    url = str(source.get("url") or "")
                    result_ref = str(source.get("result_ref") or "")
                    if not re.fullmatch(r"https://[^\s]+", url):
                        raise ValueError("invalid_external_url")
                    resolved = self.store.resolve_run_result(
                        result_ref, current_thread_id=str(message["thread_id"]),
                        current_scope_version=int(space["scope_version"]),
                    )
                    if not str(resolved["name"]).startswith("context7_") or url not in json.dumps(
                        resolved["result"], ensure_ascii=False
                    ):
                        raise ValueError("external_source_not_in_result")
                    receipt = connection.execute(
                        "SELECT completed_at FROM assistant_tool_calls WHERE run_id=? AND call_id=?",
                        (resolved["run_id"], resolved["call_id"]),
                    ).fetchone()
                    external_links.append({"url": url, "result_ref": resolved["result_ref"],
                                           "captured_at": str(receipt["completed_at"] or now)})
                if memory_id:
                    if not self._personal_dependency_current(
                        connection, space_id=space_id, memory_id=str(memory_id),
                        memory_version=int(memory_version), source_message_id=source_message_id,
                    ):
                        raise AssistantConflict("personal_dependency_stale")
                    personal_links.append((block_id, str(memory_id), int(memory_version)))
                value = {
                    "stable_id": block_id, "heading": heading[:160], "markdown": body,
                    "source_refs": revisions, "applicability": str(item.get("applicability") or "")[:600],
                    "assessment": {"source": "source_reported", "analysis": "system_synthesis",
                                   "personal": "user_explicit"}[role],
                    "relation": {"source": "discussion_source", "analysis": "discussion_analysis",
                                 "personal": "personal_note"}[role],
                    "manual_lock": role == "personal", "user_input_source": "memory_derived" if memory_id else "discussion",
                    "source_message_id": source_message_id, "created_at": now,
                    **({"external_sources": external_links} if external_links else {}),
                    **({"user_quote": quote} if role == "personal" else {}),
                }
                if role == "personal" and not memory_id:
                    historical = bool(re.search(r"当时|那时|曾经|之前|过去", body))
                    validity = None if historical else anchored_validity(body, str(message["created_at"]))
                    if validity is None and has_time_reference(body):
                        value["historical_statement"] = True
                        value["validity_note"] = "原话包含未能可靠解释的时间；仅作历史记录，当前安排需核对"
                    elif historical:
                        value["historical_statement"] = True
                    elif validity:
                        value.update(validity)
                incoming.append(value)
            version = int(before["version"]) + 1 if before else 1
            all_blocks = old_blocks + incoming
            if before:
                changed = connection.execute(
                    """UPDATE assistant_wiki_pages SET blocks_json=?,version=?,updated_at=?
                    WHERE id=? AND version=?""",
                    (json.dumps(all_blocks, ensure_ascii=False), version, now, page_id, before["version"]),
                )
                if changed.rowcount != 1:
                    raise AssistantConflict("wiki_version_conflict")
            else:
                connection.execute(
                    """INSERT INTO assistant_wiki_pages(id,principal_id,space_id,normalized_title,title,
                    aliases_json,page_type,summary,blocks_json,version,status,scope_version,created_at,updated_at)
                    VALUES(?,?,?,?,?,'[]','topic',?,?,1,'active',?,?,?)""",
                    (page_id, self.principal_id, space_id, normalized, title, purpose,
                     json.dumps(all_blocks, ensure_ascii=False), space["scope_version"], now, now),
                )
            for block_id, video_id, revision in source_links:
                connection.execute(
                    """INSERT INTO assistant_wiki_dependencies(page_id,block_id,source_revision,video_id,
                    dependency_kind,created_at) VALUES(?,?,?,?,'source',?)""",
                    (page_id, block_id, revision, video_id, now),
                )
                connection.execute(
                    """INSERT INTO assistant_wiki_materials(page_id,video_id,source_revision,relation,
                    status,created_at,updated_at) VALUES(?,?,?,'supports_block','integrated',?,?)
                    ON CONFLICT(page_id,video_id) DO UPDATE SET source_revision=excluded.source_revision,
                    relation='supports_block',updated_at=excluded.updated_at""",
                    (page_id, video_id, revision, now, now),
                )
            for block_id, memory_id, memory_version in personal_links:
                connection.execute(
                    """INSERT INTO assistant_wiki_personal_dependencies
                    (page_id,block_id,memory_id,memory_version,source_message_id,created_at)
                    VALUES(?,?,?,?,?,?)""",
                    (page_id, block_id, memory_id, memory_version, source_message_id, now),
                )
            after = self._decode_page(dict(connection.execute(
                "SELECT * FROM assistant_wiki_pages WHERE id=?", (page_id,)
            ).fetchone()))
            connection.execute(
                """INSERT INTO assistant_wiki_changes(page_id,version,operation,before_json,after_json,
                summary,actor,created_at) VALUES(?,?,'discussion_saved',?,?,?,'user',?)""",
                (page_id, version, json.dumps(before, ensure_ascii=False) if before else None,
                 json.dumps(after, ensure_ascii=False), "保存讨论成果", now),
            )
            self._fts_replace(connection, after)
            self._save_operation_state(connection, page_id, version, before_state)
            connection.execute(
                """INSERT INTO assistant_mutation_receipts
                (operation_key,principal_id,operation,result_json,created_at)
                VALUES(?,?,'knowledge_save',?,?)""",
                (operation_key, self.principal_id, json.dumps(after, ensure_ascii=False), now),
            )
        return self._visible_page(after)

    def propose_discussion(
        self, *, space_id: int, topics: list[dict[str, Any]], omitted: list[str],
        source_message_id: str, request_key: str,
    ) -> dict[str, Any]:
        if not 2 <= len(topics) <= 6 or not all(isinstance(item, dict) for item in topics):
            raise ValueError("invalid_knowledge_plan")
        space = self.store.get_space(space_id)
        with self.db.connect() as connection:
            message = connection.execute(
                """SELECT 1 FROM assistant_messages m JOIN assistant_threads t ON t.id=m.thread_id
                WHERE m.id=? AND m.role='user' AND t.principal_id=? AND t.space_id=?""",
                (source_message_id, self.principal_id, space_id),
            ).fetchone()
            if message is None:
                raise ValueError("user_source_required")
            plan_id = "akplan_" + hashlib.sha256(
                f"{self.principal_id}:{space_id}:{source_message_id}:{request_key}".encode()
            ).hexdigest()[:28]
            existing = connection.execute(
                "SELECT * FROM assistant_knowledge_plans WHERE id=?", (plan_id,)
            ).fetchone()
            if existing:
                return self._decode_knowledge_plan(dict(existing))
            prepared = []
            names = set()
            for item in topics:
                title = str(item.get("title") or "").strip()
                purpose = str(item.get("purpose") or "").strip()
                blocks = item.get("blocks") or []
                normalized = self._normalize_title(title)
                if not normalized or normalized in names or not purpose or not 1 <= len(blocks) <= 8:
                    raise ValueError("invalid_knowledge_plan_topic")
                names.add(normalized)
                page = connection.execute(
                    """SELECT id,version FROM assistant_wiki_pages WHERE principal_id=? AND space_id=?
                    AND normalized_title=? AND status='active'""",
                    (self.principal_id, space_id, normalized),
                ).fetchone()
                refs = sorted({str(ref) for block in blocks for ref in block.get("source_refs", [])})
                if refs and not self.sources.source_refs_visible(refs, self._scope(space)):
                    raise ValueError("source_out_of_scope")
                prepared.append({
                    "title": title, "purpose": purpose, "blocks": blocks,
                    "source_refs": refs, "cross_references": item.get("cross_references") or [],
                    "omitted": item.get("omitted") or [],
                    "page_id": str(page["id"]) if page else None,
                    "expected_version": int(page["version"]) if page else None,
                })
            now = utc_now()
            connection.execute(
                """INSERT INTO assistant_knowledge_plans(id,principal_id,space_id,version,scope_version,
                source_message_id,payload_json,results_json,status,created_at,updated_at)
                VALUES(?,?,?,1,?,?,?,'{}','pending',?,?)""",
                (plan_id, self.principal_id, space_id, space["scope_version"], source_message_id,
                 json.dumps({"topics": prepared, "omitted": omitted[:20]}, ensure_ascii=False), now, now),
            )
            row = connection.execute("SELECT * FROM assistant_knowledge_plans WHERE id=?", (plan_id,)).fetchone()
        return self._present_knowledge_plan(self._decode_knowledge_plan(dict(row)))

    @staticmethod
    def _decode_knowledge_plan(row: dict[str, Any]) -> dict[str, Any]:
        row["payload"] = json.loads(row.pop("payload_json"))
        row["results"] = json.loads(row.pop("results_json"))
        return row

    def _present_knowledge_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        with self.db.connect() as connection:
            for topic in plan["payload"]["topics"]:
                labels = []
                for ref in topic.get("source_refs", []):
                    parts = str(ref).split(":")
                    if len(parts) >= 2 and parts[0] == "video" and parts[1].isdigit():
                        video = connection.execute(
                            "SELECT title FROM videos WHERE id=?", (int(parts[1]),)
                        ).fetchone()
                        if video:
                            labels.append(str(video["title"]))
                topic["source_labels"] = labels
        return plan

    def list_discussion_plans(self, *, space_id: int) -> list[dict[str, Any]]:
        self.store.get_space(space_id)
        with self.db.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM assistant_knowledge_plans WHERE principal_id=? AND space_id=?
                ORDER BY created_at DESC LIMIT 30""", (self.principal_id, space_id),
            ).fetchall()
        return [self._present_knowledge_plan(self._decode_knowledge_plan(dict(row))) for row in rows]

    def revise_discussion_plan(
        self, plan_id: str, *, space_id: int, expected_version: int,
        topics: list[dict[str, Any]], omitted: list[str], operation_key: str,
    ) -> dict[str, Any]:
        if not 2 <= len(topics) <= 6:
            raise ValueError("invalid_knowledge_plan")
        space = self.store.get_space(space_id)
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            receipt = connection.execute(
                "SELECT result_json FROM assistant_mutation_receipts WHERE operation_key=? AND principal_id=?",
                (operation_key, self.principal_id),
            ).fetchone()
            if receipt:
                return json.loads(receipt["result_json"])
            row = connection.execute(
                "SELECT * FROM assistant_knowledge_plans WHERE id=? AND principal_id=? AND space_id=?",
                (plan_id, self.principal_id, space_id),
            ).fetchone()
            if row is None:
                raise KeyError(plan_id)
            plan = self._decode_knowledge_plan(dict(row))
            if plan["status"] != "pending" or int(plan["version"]) != expected_version:
                raise AssistantConflict("knowledge_plan_version_conflict")
            if int(plan["scope_version"]) != int(space["scope_version"]):
                raise AssistantConflict("knowledge_plan_scope_changed")
            names = set()
            prepared = []
            for item in topics:
                title, purpose = str(item.get("title") or "").strip(), str(item.get("purpose") or "").strip()
                blocks = item.get("blocks") or []
                normalized = self._normalize_title(title)
                if not normalized or normalized in names or len(title) > 120 or not purpose or len(purpose) > 600 or not 1 <= len(blocks) <= 8:
                    raise ValueError("invalid_knowledge_plan_topic")
                names.add(normalized)
                refs = sorted({str(ref) for block in blocks for ref in block.get("source_refs", [])})
                if refs and not self.sources.source_refs_visible(refs, self._scope(space)):
                    raise ValueError("source_out_of_scope")
                page = connection.execute(
                    """SELECT id,version FROM assistant_wiki_pages WHERE principal_id=? AND space_id=?
                    AND normalized_title=? AND status='active'""",
                    (self.principal_id, space_id, normalized),
                ).fetchone()
                prepared.append({"title": title, "purpose": purpose, "blocks": blocks,
                                 "source_refs": refs, "cross_references": item.get("cross_references") or [],
                                 "omitted": item.get("omitted") or [],
                                 "page_id": str(page["id"]) if page else None,
                                 "expected_version": int(page["version"]) if page else None})
            connection.execute(
                """UPDATE assistant_knowledge_plans SET version=version+1,payload_json=?,updated_at=?
                WHERE id=? AND version=? AND status='pending'""",
                (json.dumps({"topics": prepared, "omitted": omitted[:20]}, ensure_ascii=False),
                 utc_now(), plan_id, expected_version),
            )
            updated = self._present_knowledge_plan(self._decode_knowledge_plan(dict(connection.execute(
                "SELECT * FROM assistant_knowledge_plans WHERE id=?", (plan_id,)
            ).fetchone())))
            connection.execute(
                """INSERT INTO assistant_mutation_receipts(operation_key,principal_id,operation,result_json,created_at)
                VALUES(?,?,'knowledge_plan_revise',?,?)""",
                (operation_key, self.principal_id, json.dumps(updated, ensure_ascii=False), utc_now()),
            )
        return updated

    def decide_discussion_plan(
        self, plan_id: str, *, space_id: int, expected_version: int, accept: bool,
        operation_key: str,
    ) -> dict[str, Any]:
        # Claim the exact version before any page write. A pending plan can be
        # revised or rejected only until this transaction commits.
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM assistant_knowledge_plans WHERE id=? AND principal_id=? AND space_id=?",
                (plan_id, self.principal_id, space_id),
            ).fetchone()
            if row is None:
                raise KeyError(plan_id)
            observed = self._decode_knowledge_plan(dict(row))
            if int(observed["version"]) != expected_version:
                raise AssistantConflict("knowledge_plan_version_conflict")
        space = self.store.get_space(space_id)
        if int(space["scope_version"]) != int(observed["scope_version"]):
            raise AssistantConflict("knowledge_plan_scope_changed")
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM assistant_knowledge_plans WHERE id=? AND principal_id=? AND space_id=?",
                (plan_id, self.principal_id, space_id),
            ).fetchone()
            if row is None:
                raise KeyError(plan_id)
            plan = self._decode_knowledge_plan(dict(row))
            if int(plan["version"]) != expected_version:
                raise AssistantConflict("knowledge_plan_version_conflict")
            current_scope = connection.execute(
                "SELECT scope_version FROM assistant_spaces WHERE id=?", (space_id,),
            ).fetchone()
            if current_scope is None or int(current_scope["scope_version"]) != int(plan["scope_version"]):
                raise AssistantConflict("knowledge_plan_scope_changed")
            if not accept:
                if plan["status"] == "pending":
                    changed = connection.execute(
                        """UPDATE assistant_knowledge_plans SET status='rejected',updated_at=?
                        WHERE id=? AND version=? AND status='pending'""",
                        (utc_now(), plan_id, expected_version),
                    )
                    if changed.rowcount != 1:
                        raise AssistantConflict("knowledge_plan_state_changed")
                    plan["status"] = "rejected"
                    return plan
                if plan["status"] == "rejected":
                    return plan
                raise AssistantConflict("knowledge_plan_already_accepted")
            if plan["status"] == "rejected":
                raise AssistantConflict("knowledge_plan_rejected")
            if plan["status"] == "completed":
                return plan
            if plan["status"] == "pending":
                changed = connection.execute(
                    """UPDATE assistant_knowledge_plans SET status='partial',updated_at=?
                    WHERE id=? AND version=? AND status='pending'""",
                    (utc_now(), plan_id, expected_version),
                )
                if changed.rowcount != 1:
                    raise AssistantConflict("knowledge_plan_state_changed")
                plan["status"] = "partial"
            elif plan["status"] != "partial":
                raise AssistantConflict("knowledge_plan_state_changed")
        for index, item in enumerate(plan["payload"]["topics"]):
            key = str(index)
            with self.db.connect() as connection:
                live = self._decode_knowledge_plan(dict(connection.execute(
                    "SELECT * FROM assistant_knowledge_plans WHERE id=?", (plan_id,),
                ).fetchone()))
            if live["results"].get(key, {}).get("status") == "completed":
                continue
            try:
                page = self.save_discussion(
                    space_id=space_id, title=item["title"], purpose=item["purpose"],
                    blocks=item["blocks"], expected_version=item["expected_version"],
                    source_message_id=plan["source_message_id"],
                    operation_key=f"knowledge-plan:{plan_id}:{expected_version}:{index}",
                    authorized_plan_id=plan_id, authorized_plan_version=expected_version,
                )
                outcome = {"status": "completed", "page_id": page["id"],
                           "version": page["version"]}
            except (ValueError, AssistantConflict, KeyError) as exc:
                outcome = {"status": "failed", "reason": str(exc)}
            with self.db.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                current = self._decode_knowledge_plan(dict(connection.execute(
                    "SELECT * FROM assistant_knowledge_plans WHERE id=?", (plan_id,),
                ).fetchone()))
                if int(current["version"]) != expected_version or current["status"] not in {"partial", "completed"}:
                    raise AssistantConflict("knowledge_plan_state_changed")
                results = dict(current["results"])
                if results.get(key, {}).get("status") != "completed":
                    results[key] = outcome
                status = ("completed" if all(results.get(str(i), {}).get("status") == "completed"
                                             for i in range(len(plan["payload"]["topics"]))) else "partial")
                connection.execute(
                    """UPDATE assistant_knowledge_plans SET results_json=?,status=?,updated_at=?
                    WHERE id=? AND version=?""",
                    (json.dumps(results, ensure_ascii=False), status, utc_now(), plan_id, expected_version),
                )
        with self.db.connect() as connection:
            latest = self._decode_knowledge_plan(dict(connection.execute(
                "SELECT * FROM assistant_knowledge_plans WHERE id=?", (plan_id,),
            ).fetchone()))
        return {**latest, "operation_key": operation_key}

    def _personal_dependency_current(
        self, connection: Any, *, space_id: int, memory_id: str,
        memory_version: int, source_message_id: str | None,
    ) -> bool:
        row = connection.execute(
            "SELECT * FROM assistant_memories WHERE id=? AND principal_id=?",
            (memory_id, self.principal_id),
        ).fetchone()
        if row is None:
            return False
        memory = dict(row)
        if (memory["status"] != "active" or int(memory["version"]) != memory_version or
                not MemoryService._is_currently_valid(memory) or
                not (memory["scope_kind"] == "user" or
                     (memory["scope_kind"] == "space" and str(memory["scope_id"]) == str(space_id)))):
            return False
        if source_message_id:
            message = connection.execute(
                """SELECT 1 FROM assistant_messages m JOIN assistant_threads t ON t.id=m.thread_id
                WHERE m.id=? AND m.role='user' AND t.principal_id=? AND t.space_id=?""",
                (source_message_id, self.principal_id, space_id),
            ).fetchone()
            if message is None:
                return False
            suppressions = connection.execute(
                """SELECT source_message_ids_json FROM assistant_memory_suppressions
                WHERE principal_id=? AND (scope_kind='user' OR (scope_kind='space' AND scope_id=?))""",
                (self.principal_id, str(space_id)),
            ).fetchall()
            if any(source_message_id in json.loads(item["source_message_ids_json"] or "[]")
                   for item in suppressions):
                return False
        return True

    def changes(self, page_id: str) -> list[dict[str, Any]]:
        self.get_page(page_id, include_hidden=True)
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT version, operation, summary, actor, created_at
                FROM assistant_wiki_changes WHERE page_id=? ORDER BY version DESC
                """,
                (page_id,),
            ).fetchall()
            states = {int(row["version"]) for row in connection.execute(
                "SELECT version FROM assistant_wiki_operation_states WHERE page_id=?",
                (page_id,),
            ).fetchall()}
        return [{**dict(row), "can_revert": int(row["version"]) in states or
                 int(row["version"]) + 1 in states} for row in rows]

    def merge_pages(
        self, source_page_id: str, target_page_id: str, *, space_id: int,
        source_version: int, target_version: int, operation_key: str,
        accept_conflict: bool = False,
        _connection: Any | None = None,
    ) -> dict[str, Any]:
        """Merge two explicit same-scope topics, or hold a concrete manual conflict."""
        if source_page_id == target_page_id:
            raise ValueError("same_wiki_page")
        now = utc_now()
        with (self.db.connect() if _connection is None else nullcontext(_connection)) as connection:
            if _connection is None:
                connection.execute("BEGIN IMMEDIATE")
            receipt = connection.execute(
                "SELECT result_json FROM assistant_mutation_receipts WHERE operation_key=? AND principal_id=?",
                (operation_key, self.principal_id),
            ).fetchone()
            if receipt is not None:
                return json.loads(receipt["result_json"])
            rows = connection.execute(
                """SELECT * FROM assistant_wiki_pages WHERE id IN (?,?) AND principal_id=?
                AND space_id=? AND status='active'""",
                (source_page_id, target_page_id, self.principal_id, space_id),
            ).fetchall()
            by_id = {str(row["id"]): self._decode_page(dict(row)) for row in rows}
            if set(by_id) != {source_page_id, target_page_id}:
                raise KeyError("wiki_merge_page_missing")
            source, target = by_id[source_page_id], by_id[target_page_id]
            if int(source["version"]) != source_version or int(target["version"]) != target_version:
                raise AssistantConflict("wiki_version_conflict")
            visible_source = self._visible_page(source)
            visible_target = self._visible_page(target)
            if not visible_source["blocks"]:
                raise AssistantConflict("wiki_source_has_no_current_content")
            manual_target = {str(block["heading"]).strip().casefold(): block
                             for block in visible_target["blocks"] if block.get("manual_lock")}
            conflicts = [block for block in visible_source["blocks"] if block.get("manual_lock")
                         and str(block["heading"]).strip().casefold() in manual_target
                         and str(block["markdown"]) != str(manual_target[str(block["heading"]).strip().casefold()]["markdown"])]
            fingerprint = hashlib.sha256(json.dumps({
                "source": source_page_id, "target": target_page_id,
                "source_version": source_version, "target_version": target_version,
                "conflicts": [block["stable_id"] for block in conflicts],
            }, sort_keys=True).encode("utf-8")).hexdigest()
            if conflicts and not accept_conflict:
                proposal = connection.execute(
                    """SELECT id,status FROM assistant_wiki_proposals
                    WHERE principal_id=? AND space_id=? AND kind='merge'
                      AND target_page_id=? AND input_fingerprint=?""",
                    (self.principal_id, space_id, target_page_id, fingerprint),
                ).fetchone()
                if proposal is None:
                    proposal_id = f"awprop_{uuid.uuid4().hex}"
                    connection.execute(
                        """INSERT INTO assistant_wiki_proposals(
                            id,principal_id,space_id,kind,source_page_id,target_page_id,
                            source_version,target_version,input_fingerprint,payload_json,
                            status,created_at,updated_at
                        ) VALUES(?,?,?,'merge',?,?,?,?,?,?,'pending',?,?)""",
                        (proposal_id, self.principal_id, space_id, source_page_id,
                         target_page_id, source_version, target_version, fingerprint,
                         json.dumps({"conflict_block_ids": [block["stable_id"] for block in conflicts]}),
                         now, now),
                    )
                    status = "pending"
                else:
                    proposal_id, status = str(proposal["id"]), str(proposal["status"])
                return {"status": status, "proposal_id": proposal_id,
                        "reason": "manual_content_conflict"}
            source_before = self._operation_state(connection, source_page_id)
            target_before = self._operation_state(connection, target_page_id)
            target_blocks = list(target["blocks"])
            target_ids = {str(block["stable_id"]) for block in target_blocks}
            mapped_ids: dict[str, str] = {}
            for block in visible_source["blocks"]:
                candidate = dict(block)
                old_id = str(candidate["stable_id"])
                if old_id in target_ids:
                    existing = next(item for item in target_blocks if item["stable_id"] == old_id)
                    if all(existing.get(field) == candidate.get(field) for field in
                           ("markdown", "heading", "source_refs", "assessment")):
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
                """UPDATE assistant_wiki_pages SET blocks_json=?,summary=?,version=?,updated_at=?
                WHERE id=? AND version=?""",
                (json.dumps(target_blocks, ensure_ascii=False),
                 "已合并相关主题；不同说法请按各块条件和来源查看。",
                 target_next, now, target_page_id, target_version),
            )
            for item in source_before["sources"]:
                if str(item["block_id"]) in mapped_ids:
                    connection.execute(
                        """INSERT OR IGNORE INTO assistant_wiki_dependencies(
                            page_id,block_id,source_revision,video_id,dependency_kind,created_at
                        ) VALUES(?,?,?,?,?,?)""",
                        (target_page_id, mapped_ids[str(item["block_id"])], item["source_revision"],
                         item["video_id"], item["dependency_kind"], now),
                    )
            for item in source_before["personal"]:
                if str(item["block_id"]) in mapped_ids:
                    connection.execute(
                        """INSERT OR IGNORE INTO assistant_wiki_personal_dependencies(
                            page_id,block_id,memory_id,memory_version,source_message_id,created_at
                        ) VALUES(?,?,?,?,?,?)""",
                        (target_page_id, mapped_ids[str(item["block_id"])], item["memory_id"],
                         item["memory_version"], item["source_message_id"], now),
                    )
            for item in source_before["materials"]:
                connection.execute(
                    """INSERT OR IGNORE INTO assistant_wiki_materials(
                        page_id,video_id,source_revision,relation,status,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?)""",
                    (target_page_id, item["video_id"], item["source_revision"],
                     item["relation"], item["status"], now, now),
                )
            connection.execute(
                "UPDATE assistant_wiki_pages SET status='merged',version=?,updated_at=? WHERE id=? AND version=?",
                (source_next, now, source_page_id, source_version),
            )
            connection.execute(
                """INSERT INTO assistant_wiki_redirects(old_page_id,target_page_id,space_id,created_at)
                VALUES(?,?,?,?)""", (source_page_id, target_page_id, space_id, now),
            )
            connection.execute("DELETE FROM assistant_wiki_fts WHERE page_id=?", (source_page_id,))
            target_after = self._operation_state(connection, target_page_id)["page"]
            source_after = self._operation_state(connection, source_page_id)["page"]
            for page_id, version, before_page, after_page in (
                (target_page_id, target_next, target, target_after),
                (source_page_id, source_next, source, source_after),
            ):
                connection.execute(
                    """INSERT INTO assistant_wiki_changes(
                        page_id,version,operation,before_json,after_json,summary,actor,created_at
                    ) VALUES(?,?,'merged',?,?,?,'user',?)""",
                    (page_id, version, json.dumps(before_page, ensure_ascii=False),
                     json.dumps(after_page, ensure_ascii=False),
                     f"合并主题 {source['title']} → {target['title']}", now),
                )
            self._fts_replace(connection, target_after)
            self._save_operation_state(connection, target_page_id, target_next, target_before)
            self._save_operation_state(connection, source_page_id, source_next, source_before)
            result = {"status": "merged", "page_id": target_page_id, "version": target_next,
                      "redirected_page_id": source_page_id}
            connection.execute(
                """INSERT INTO assistant_mutation_receipts(
                    operation_key,principal_id,operation,result_json,created_at
                ) VALUES(?,?,'wiki_merge',?,?)""",
                (operation_key, self.principal_id, json.dumps(result), now),
            )
        return result

    def decide_proposal(self, proposal_id: str, *, accept: bool, operation_key: str,
                        space_id: int | None = None) -> dict[str, Any]:
        stale = False
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM assistant_wiki_proposals WHERE id=? AND principal_id=?",
                (proposal_id, self.principal_id),
            ).fetchone()
            if row is None:
                raise KeyError(proposal_id)
            proposal = dict(row)
            if space_id is not None and int(proposal["space_id"]) != space_id:
                raise KeyError(proposal_id)
            receipt = connection.execute(
                "SELECT result_json FROM assistant_mutation_receipts WHERE operation_key=? AND principal_id=?",
                (operation_key, self.principal_id),
            ).fetchone()
            if receipt is not None:
                result = json.loads(receipt["result_json"])
                if result.get("proposal_id") != proposal_id:
                    raise AssistantConflict("operation_key_conflict")
                return result
            merge_key = f"wiki_proposal_merge:{proposal_id}"
            if proposal["status"] != "pending":
                merged = connection.execute(
                    "SELECT result_json FROM assistant_mutation_receipts WHERE operation_key=? AND principal_id=?",
                    (merge_key, self.principal_id),
                ).fetchone() if proposal["status"] == "accepted" else None
                return {**(json.loads(merged["result_json"]) if merged else {}),
                        "status": proposal["status"], "proposal_id": proposal_id}
            if not any(item["id"] == proposal_id for item in
                       self.list_proposals(space_id=int(proposal["space_id"]))):
                connection.execute(
                    "UPDATE assistant_wiki_proposals SET status='stale',updated_at=? WHERE id=?",
                    (utc_now(), proposal_id),
                )
                stale = True
                result = {"status": "stale", "proposal_id": proposal_id}
            elif not accept:
                connection.execute(
                    "UPDATE assistant_wiki_proposals SET status='rejected',updated_at=? WHERE id=? AND status='pending'",
                    (utc_now(), proposal_id),
                )
                result = {"status": "rejected", "proposal_id": proposal_id}
            else:
                merged = self.merge_pages(
                    str(proposal["source_page_id"]), str(proposal["target_page_id"]),
                    space_id=int(proposal["space_id"]),
                    source_version=int(proposal["source_version"]),
                    target_version=int(proposal["target_version"]),
                    operation_key=merge_key, accept_conflict=True, _connection=connection,
                )
                changed = connection.execute(
                    "UPDATE assistant_wiki_proposals SET status='accepted',updated_at=? WHERE id=? AND status='pending'",
                    (utc_now(), proposal_id),
                )
                if changed.rowcount != 1:
                    raise AssistantConflict("wiki_proposal_stale")
                result = {**merged, "status": "accepted", "proposal_id": proposal_id}
            if not stale:
                connection.execute(
                    """INSERT INTO assistant_mutation_receipts(
                        operation_key,principal_id,operation,result_json,created_at
                    ) VALUES(?,?,'wiki_proposal_decision',?,?)""",
                    (operation_key, self.principal_id, json.dumps(result), utc_now()),
                )
        if stale:
            raise AssistantConflict("wiki_proposal_stale")
        return result

    def list_proposals(self, *, space_id: int) -> list[dict[str, Any]]:
        self.store.get_space(space_id)
        with self.db.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM assistant_wiki_proposals
                WHERE principal_id=? AND space_id=? AND status='pending'
                ORDER BY created_at DESC""",
                (self.principal_id, space_id),
            ).fetchall()
        values = []
        for row in rows:
            item = dict(row)
            try:
                source = self.get_page(str(item["source_page_id"]), space_id=space_id)
                target = self.get_page(str(item["target_page_id"]), space_id=space_id)
            except KeyError:
                continue
            if (int(source["version"]) != int(item["source_version"]) or
                    int(target["version"]) != int(item["target_version"])):
                continue
            ids = set(json.loads(item["payload_json"]).get("conflict_block_ids", []))
            differences = []
            for block in source["blocks"]:
                if block["stable_id"] not in ids:
                    continue
                counterpart = next((candidate for candidate in target["blocks"]
                                    if candidate.get("manual_lock") and
                                    str(candidate["heading"]).strip().casefold() ==
                                    str(block["heading"]).strip().casefold()), None)
                if counterpart is not None:
                    differences.append({
                        "heading": block["heading"], "source_text": block["markdown"],
                        "target_text": counterpart["markdown"],
                    })
            if not differences:
                continue
            values.append({"id": item["id"], "kind": "merge",
                           "source_page_id": source["id"], "source_title": source["title"],
                           "target_page_id": target["id"], "target_title": target["title"],
                           "differences": differences})
        return values

    def revert(
        self,
        page_id: str,
        *,
        target_version: int,
        expected_version: int,
        operation_key: str,
    ) -> dict[str, Any]:
        now = utc_now()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            receipt = connection.execute(
                "SELECT result_json FROM assistant_mutation_receipts WHERE operation_key=? AND principal_id=?",
                (operation_key, self.principal_id),
            ).fetchone()
            if receipt is not None:
                return self._visible_page(json.loads(receipt["result_json"]))
            row = connection.execute(
                "SELECT * FROM assistant_wiki_pages WHERE id=? AND principal_id=?",
                (page_id, self.principal_id),
            ).fetchone()
            if row is None:
                raise KeyError(page_id)
            before = self._decode_page(dict(row))
            before_state = self._operation_state(connection, page_id)
            if int(before["version"]) != expected_version:
                raise AssistantConflict("wiki_version_conflict")
            if target_version >= expected_version:
                raise ValueError("invalid_revert_version")
            state_row = connection.execute(
                "SELECT after_json FROM assistant_wiki_operation_states WHERE page_id=? AND version=?",
                (page_id, target_version),
            ).fetchone()
            if state_row is not None:
                target_state = json.loads(state_row["after_json"])
            else:
                state_row = connection.execute(
                    "SELECT before_json FROM assistant_wiki_operation_states WHERE page_id=? AND version=?",
                    (page_id, target_version + 1),
                ).fetchone()
                if state_row is None or not state_row["before_json"]:
                    raise AssistantConflict("revert_dependency_snapshot_unavailable")
                target_state = json.loads(state_row["before_json"])
            later_changes = connection.execute(
                """SELECT operation,before_json,after_json FROM assistant_wiki_changes
                WHERE page_id=? AND version>? ORDER BY version""",
                (page_id, target_version + 1),
            ).fetchall()
            if any(str(item["operation"]) not in {"block_edited", "personal_note_added"}
                   for item in later_changes):
                raise AssistantConflict("revert_later_source_change_conflict")
            independent_ids: set[str] = set()
            for item in later_changes:
                old = {str(block["stable_id"]): block for block in
                       json.loads(item["before_json"] or "{}").get("blocks", [])}
                new = {str(block["stable_id"]): block for block in
                       json.loads(item["after_json"]).get("blocks", [])}
                independent_ids.update(block_id for block_id, block in new.items()
                                       if block.get("manual_lock") and block != old.get(block_id))
            target = target_state["page"]
            desired_sources = target_state["sources"]
            desired_personal = target_state["personal"]
            current_blocks = {str(block["stable_id"]): block for block in before["blocks"]}
            desired_blocks = {str(block["stable_id"]): block for block in target["blocks"]}
            restored_blocks = []
            for block_id, block in desired_blocks.items():
                restored_blocks.append(current_blocks[block_id] if block_id in independent_ids
                                       and block_id in current_blocks else block)
            for block_id in sorted(independent_ids - desired_blocks.keys()):
                if block_id in current_blocks:
                    restored_blocks.append(current_blocks[block_id])
            space = self.store.get_space(int(before["space_id"]))
            visible_ids = set(self.sources.visible_video_ids(self._scope(space)))
            valid_source_revisions = {
                str(item["source_revision"]) for item in connection.execute(
                    """SELECT h.current_revision AS source_revision,h.video_id
                    FROM assistant_source_heads h WHERE h.principal_id=?""",
                    (self.principal_id,),
                ).fetchall() if int(item["video_id"]) in visible_ids
            }
            current_source_rows = [item for item in before_state["sources"]
                                   if str(item["block_id"]) in independent_ids]
            source_rows = [item for item in desired_sources
                           if str(item["block_id"]) not in independent_ids] + current_source_rows
            current_personal_rows = [item for item in before_state["personal"]
                                     if str(item["block_id"]) in independent_ids]
            personal_rows = [item for item in desired_personal
                             if str(item["block_id"]) not in independent_ids] + current_personal_rows
            kept_blocks = []
            for block in restored_blocks:
                block_id = str(block["stable_id"])
                refs = {str(item["source_revision"]) for item in source_rows
                        if str(item["block_id"]) == block_id}
                if block.get("source_refs") and (not refs or not refs.issubset(valid_source_revisions)):
                    continue
                deps = [item for item in personal_rows if str(item["block_id"]) == block_id]
                if deps and not all(self._personal_dependency_current(
                    connection, space_id=int(before["space_id"]),
                    memory_id=str(item["memory_id"]),
                    memory_version=int(item["memory_version"]),
                    source_message_id=item["source_message_id"],
                ) for item in deps):
                    continue
                kept_blocks.append(block)
            kept_ids = {str(block["stable_id"]) for block in kept_blocks}
            source_rows = [item for item in source_rows if str(item["block_id"]) in kept_ids]
            personal_rows = [item for item in personal_rows if str(item["block_id"]) in kept_ids]
            version = expected_version + 1
            updated = connection.execute(
                """
                UPDATE assistant_wiki_pages SET title=?, normalized_title=?, page_type=?,
                    summary=?, blocks_json=?, version=?, updated_at=?
                WHERE id=? AND version=?
                """,
                (
                    target["title"], self._normalize_title(target["title"]),
                    target["page_type"], self._pending_guide(),
                    json.dumps(kept_blocks, ensure_ascii=False), version, now,
                    page_id, expected_version,
                ),
            )
            if updated.rowcount != 1:
                raise AssistantConflict("wiki_version_conflict")
            connection.execute("DELETE FROM assistant_wiki_dependencies WHERE page_id=?", (page_id,))
            for item in source_rows:
                connection.execute(
                    """INSERT INTO assistant_wiki_dependencies(
                        page_id,block_id,source_revision,video_id,dependency_kind,created_at
                    ) VALUES(?,?,?,?,?,?)""",
                    (page_id, item["block_id"], item["source_revision"],
                     item["video_id"], item["dependency_kind"], now),
                )
            connection.execute("DELETE FROM assistant_wiki_personal_dependencies WHERE page_id=?", (page_id,))
            for item in personal_rows:
                connection.execute(
                    """INSERT INTO assistant_wiki_personal_dependencies(
                        page_id,block_id,memory_id,memory_version,source_message_id,created_at
                    ) VALUES(?,?,?,?,?,?)""",
                    (page_id, item["block_id"], item["memory_id"],
                     item["memory_version"], item["source_message_id"], now),
                )
            connection.execute("DELETE FROM assistant_wiki_materials WHERE page_id=?", (page_id,))
            for item in target_state["materials"]:
                if str(item["source_revision"]) not in valid_source_revisions:
                    continue
                connection.execute(
                    """INSERT INTO assistant_wiki_materials(
                        page_id,video_id,source_revision,relation,status,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?)""",
                    (page_id, item["video_id"], item["source_revision"],
                     item["relation"], item["status"], now, now),
                )
            old_redirects = {str(item["old_page_id"]) for item in target_state["redirects"]}
            current_redirects = {str(item["old_page_id"]) for item in before_state["redirects"]}
            for old_page_id in current_redirects - old_redirects:
                source_row = connection.execute(
                    "SELECT * FROM assistant_wiki_pages WHERE id=? AND status='merged'",
                    (old_page_id,),
                ).fetchone()
                if source_row is None:
                    raise AssistantConflict("revert_merge_source_changed")
                source_before = self._operation_state(connection, old_page_id)
                source_version = int(source_row["version"])
                last_source_change = connection.execute(
                    "SELECT operation FROM assistant_wiki_changes WHERE page_id=? AND version=?",
                    (old_page_id, source_version),
                ).fetchone()
                if last_source_change is None or str(last_source_change["operation"]) != "merged":
                    raise AssistantConflict("revert_merge_source_changed")
                connection.execute("DELETE FROM assistant_wiki_redirects WHERE old_page_id=?", (old_page_id,))
                connection.execute(
                    "UPDATE assistant_wiki_pages SET status='active',version=?,updated_at=? WHERE id=?",
                    (source_version + 1, now, old_page_id),
                )
                source_after = self._operation_state(connection, old_page_id)["page"]
                connection.execute(
                    """INSERT INTO assistant_wiki_changes(
                        page_id,version,operation,before_json,after_json,summary,actor,created_at
                    ) VALUES(?,?,'merge_undone',?,?,?,'user',?)""",
                    (old_page_id, source_version + 1,
                     json.dumps(source_before["page"], ensure_ascii=False),
                     json.dumps(source_after, ensure_ascii=False),
                     "撤销合并，恢复原主题入口", now),
                )
                self._save_operation_state(connection, old_page_id, source_version + 1, source_before)
                self._fts_replace(connection, self._visible_page(source_after))
            after = self._decode_page(dict(connection.execute(
                "SELECT * FROM assistant_wiki_pages WHERE id=?", (page_id,)
            ).fetchone()))
            connection.execute(
                """
                INSERT INTO assistant_wiki_changes(
                    page_id, version, operation, before_json, after_json, summary, actor, created_at
                ) VALUES(?, ?, 'reverted', ?, ?, ?, 'user', ?)
                """,
                (
                    page_id, version, json.dumps(before, ensure_ascii=False),
                    json.dumps(after, ensure_ascii=False), f"恢复到版本 {target_version}", now,
                ),
            )
            self._fts_replace(connection, after)
            self._save_operation_state(connection, page_id, version, before_state)
            connection.execute(
                """
                INSERT INTO assistant_mutation_receipts(
                    operation_key, principal_id, operation, result_json, created_at
                ) VALUES(?, ?, 'wiki_revert', ?, ?)
                """,
                (operation_key, self.principal_id, json.dumps(after, ensure_ascii=False), now),
            )
        return self._visible_page(after)

    def get_source_card(self, revision: str) -> dict[str, Any] | None:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT card_json FROM assistant_source_cards WHERE revision=?", (revision,)
            ).fetchone()
        return json.loads(row["card_json"]) if row else None

    def _commit_source_card(
        self, captured: CapturedSource, *, input_hash: str, card: dict[str, Any]
    ) -> None:
        now = utc_now()
        video_id = int(captured.snapshot["metadata"]["id"])
        with self.db.connect() as connection:
            head = connection.execute(
                "SELECT current_revision FROM assistant_source_heads WHERE video_id=? AND principal_id=?",
                (video_id, self.principal_id),
            ).fetchone()
            if head is None or str(head["current_revision"]) != captured.revision:
                raise AssistantConflict("source_revision_changed")
            connection.execute(
                """
                INSERT INTO assistant_source_cards(
                    revision, video_id, input_hash, card_json, coverage,
                    extraction_version, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(revision) DO UPDATE SET
                    input_hash=excluded.input_hash, card_json=excluded.card_json,
                    coverage=excluded.coverage, extraction_version=excluded.extraction_version,
                    updated_at=excluded.updated_at
                WHERE assistant_source_cards.extraction_version<>excluded.extraction_version
                """,
                (
                    captured.revision, video_id, input_hash,
                    json.dumps(card, ensure_ascii=False), card["coverage"],
                    self.EXTRACTION_VERSION, now, now,
                ),
            )

    def _enqueue_integrations(self, video_id: int, revision: str,
                              *, batch_id: str | None = None,
                              task_topic: str | None = None,
                              request_key: str | None = None,
                              source_message_id: str | None = None) -> list[str]:
        jobs: list[str] = []
        if request_key:
            spaces = [self.store.get_space(int(str(request_key).split(":", 1)[0]))]
        elif batch_id:
            with self.db.connect() as connection:
                row = connection.execute(
                    "SELECT space_id FROM assistant_maintenance_batches WHERE id=?", (batch_id,)
                ).fetchone()
            spaces = [self.store.get_space(int(row["space_id"]))] if row else []
        else:
            spaces = [space for space in self._spaces_for_video(video_id)
                      if space.get("maintenance_mode") == "automatic"]
        for space in spaces:
            if video_id not in self.sources.visible_video_ids(self._scope(space)):
                continue
            card = self.get_source_card(revision)
            topics = [str(task_topic)] if task_topic else [
                str(value) for value in (card or {}).get("topics", [])[:5] if str(value).strip()
            ]
            if not topics:
                topics = [str((card or {}).get("title") or "未命名材料")]
            if not task_topic:
                with self.db.connect() as connection:
                    linked_topics = [str(row["title"]) for row in connection.execute(
                        """SELECT p.title FROM assistant_wiki_materials m
                        JOIN assistant_wiki_pages p ON p.id=m.page_id
                        WHERE m.video_id=? AND p.space_id=? AND p.status='active'""",
                        (video_id, int(space["id"])),
                    ).fetchall()]
                primary = topics[0]
                candidates = [
                    topic for topic in topics[1:]
                    if self._find_page(int(space["id"]), topic) is not None or
                    self._find_related_page(int(space["id"]), {"topics": [topic]}) is not None
                ]
                topics = [primary, *candidates, *linked_topics] if batch_id else [
                    topic for topic in topics
                    if self._find_page(int(space["id"]), topic) is not None or
                    self._find_related_page(int(space["id"]), {"topics": [topic]}) is not None
                ] + linked_topics
            for topic in dict.fromkeys(topics):
              with self.db.connect() as connection:
                jobs.append(self.store.enqueue_job(
                    connection,
                    kind="wiki_integrate",
                    dedupe_key=(
                        f"wiki_integrate:{space['id']}:{revision}:{self.COMPILER_VERSION}:"
                        f"{hashlib.sha256(topic.encode('utf-8')).hexdigest()[:16]}"
                        + (f":batch:{batch_id}" if batch_id else "")
                        + (f":task:{request_key}" if request_key else "")
                    ),
                    payload={
                        "space_id": space["id"], "scope_version": space["scope_version"],
                        "video_id": video_id, "revision": revision,
                        "compiler_version": self.COMPILER_VERSION, "topic": topic,
                        **({"task_topic": topic, "request_key": request_key} if request_key else {}),
                        **({"source_message_id": source_message_id} if source_message_id else {}),
                        **({"maintenance_batch_id": batch_id} if batch_id else {}),
                    },
                ))
        return jobs

    def _spaces_for_video(self, video_id: int) -> list[dict[str, Any]]:
        values = []
        for space in self.store.list_spaces():
            if video_id in self.sources.visible_video_ids(self._scope(space)):
                values.append(space)
        return values

    @staticmethod
    def _pending_guide() -> str:
        return "导读未随本次修改重写；请查看下方各条内容、条件及来源。"

    def _visible_page(self, page: dict[str, Any]) -> dict[str, Any]:
        space = self.store.get_space(int(page["space_id"]))
        visible_video_ids = set(self.sources.visible_video_ids(self._scope(space)))
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT d.block_id, d.video_id, d.source_revision, h.current_revision,
                       c.card_json, v.video_url
                FROM assistant_wiki_dependencies d
                LEFT JOIN assistant_source_cards c ON c.revision=d.source_revision
                LEFT JOIN videos v ON v.id=d.video_id
                LEFT JOIN assistant_source_heads h ON h.video_id=d.video_id
                    AND h.principal_id=?
                WHERE d.page_id=?
                """,
                (self.principal_id, page["id"]),
            ).fetchall()
            personal_rows = connection.execute(
                """SELECT block_id,memory_id,memory_version,source_message_id
                FROM assistant_wiki_personal_dependencies WHERE page_id=?""",
                (page["id"],),
            ).fetchall()
            valid_personal = {
                str(item["block_id"]): self._personal_dependency_current(
                    connection, space_id=int(page["space_id"]),
                    memory_id=str(item["memory_id"]),
                    memory_version=int(item["memory_version"]),
                    source_message_id=item["source_message_id"],
                ) for item in personal_rows
            }
            material_rows = connection.execute(
                """SELECT m.video_id,m.source_revision,m.relation,m.status,
                          h.current_revision,c.card_json,v.video_url
                FROM assistant_wiki_materials m
                LEFT JOIN assistant_source_heads h ON h.video_id=m.video_id AND h.principal_id=?
                LEFT JOIN assistant_source_cards c ON c.revision=m.source_revision
                LEFT JOIN videos v ON v.id=m.video_id
                WHERE m.page_id=? ORDER BY m.created_at,m.video_id""",
                (self.principal_id, page["id"]),
            ).fetchall()
        dependencies: dict[str, set[int]] = {}
        current_dependencies: dict[str, set[int]] = {}
        source_details: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            dependencies.setdefault(str(row["block_id"]), set()).add(int(row["video_id"]))
            if (int(row["video_id"]) in visible_video_ids and
                    str(row["current_revision"] or "") == str(row["source_revision"])):
                current_dependencies.setdefault(str(row["block_id"]), set()).add(int(row["video_id"]))
            if int(row["video_id"]) in current_dependencies.get(str(row["block_id"]), set()) and row["card_json"]:
                card = json.loads(row["card_json"])
                source_details.setdefault(str(row["block_id"]), []).append({
                    "title": card.get("title") or "未命名材料",
                    "uploader": card.get("uploader") or "",
                    "published_at": card.get("published_at"),
                    "collected_at": max(
                        (item.get("favorite_time") for item in card.get("memberships", [])
                         if item.get("favorite_time") is not None),
                        default=None,
                    ),
                    "coverage": card.get("coverage") or "metadata_only",
                    "url": str(row["video_url"] or ""),
                    "material_view": card.get("material_kind") or "未知",
                })
        blocks = []
        for block in page["blocks"]:
            if block.get("expires_at"):
                try:
                    if datetime.fromisoformat(str(block["expires_at"]).replace("Z", "+00:00")) <= datetime.fromisoformat(utc_now()):
                        continue
                except ValueError:
                    continue
            if block["stable_id"] in valid_personal and not valid_personal[block["stable_id"]]:
                continue
            if block.get("external_sources"):
                with self.db.connect() as connection:
                    message_thread = connection.execute(
                        "SELECT thread_id FROM assistant_messages WHERE id=?",
                        (block.get("source_message_id"),),
                    ).fetchone()
                if message_thread is None:
                    continue
                try:
                    for external in block["external_sources"]:
                        self.store.resolve_run_result(
                            str(external["result_ref"]),
                            current_thread_id=str(message_thread["thread_id"]),
                            current_scope_version=int(space["scope_version"]),
                        )
                except (KeyError, ValueError):
                    continue
            block_dependencies = dependencies.get(block["stable_id"], set())
            if ((block.get("source_refs") and not block_dependencies) or
                    (block_dependencies and
                     current_dependencies.get(block["stable_id"], set()) != block_dependencies)):
                continue
            value = dict(block)
            if not value.get("speaker_verified"):
                value["speaker"] = ""
            if value.get("cited_source") and not self._reference_like(str(value["cited_source"])):
                value["cited_source"] = ""
            for field in ("markdown", "heading", "applicability"):
                clean = re.sub(r"coverage=[a-z_]+", "当前可用材料", str(value.get(field) or ""))
                value[field] = re.sub(r"material_kind=[a-z_]+", "摘要材料视图", clean)
            value["sources"] = source_details.get(block["stable_id"], [])
            blocks.append(value)
        value = dict(page)
        value["blocks"] = blocks
        value["materials"] = [{
            "video_id": int(item["video_id"]),
            "title": str((json.loads(item["card_json"]) if item["card_json"] else {}).get("title") or "材料"),
            "url": str(item["video_url"] or ""),
            "relation": str(item["relation"]),
            "status": str(item["status"]),
        } for item in material_rows if int(item["video_id"]) in visible_video_ids
           and str(item["source_revision"]) == str(item["current_revision"] or "")]
        value["summary"] = re.sub(r"coverage=[a-z_]+", "当前可用材料", str(value.get("summary") or ""))
        value["availability"] = "full" if len(blocks) == len(page["blocks"]) else "partial"
        current_source_blocks = [block for block in blocks if block.get("source_refs") or block.get("external_sources")]
        visible_block_ids = {str(block["stable_id"]) for block in blocks}
        missing_source = any(
            block.get("source_refs") and str(block["stable_id"]) not in visible_block_ids
            for block in page["blocks"]
        )
        if value["availability"] == "partial" or not current_source_blocks:
            if current_source_blocks:
                notice = (
                    "部分来源已失效；以下仅展示当前有效的来源内容和个人笔记。"
                    if missing_source else
                    "部分依赖个人内容已失效；来源内容和独立个人笔记仍可查看。"
                )
                value["summary"] = f"{notice} {value['summary']}"
            elif blocks and any(block.get("assessment") == "system_synthesis" for block in blocks):
                value["summary"] = str(page.get("summary") or "")
            elif blocks:
                value["summary"] = "主题正文暂不可用；以下仅保留独立个人笔记。"
            else:
                value["summary"] = "暂无当前可用的主题正文。"
        return value

    def personal_dependency_refs(self, page_id: str, *, space_id: int) -> list[str]:
        page = self.get_page(page_id, space_id=space_id)
        visible = {str(block["stable_id"]) for block in page["blocks"]}
        with self.db.connect() as connection:
            rows = connection.execute(
                """SELECT block_id,memory_id,memory_version FROM assistant_wiki_personal_dependencies
                WHERE page_id=?""", (page_id,),
            ).fetchall()
        return sorted({f"memory:{row['memory_id']}:{int(row['memory_version'])}"
                       for row in rows if str(row["block_id"]) in visible})

    def _extract_batch(
        self,
        provider: StructuredProvider,
        *,
        snapshot: dict[str, Any],
        material_kind: str,
        material: str,
        batch_index: int,
        batch_total: int,
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
        self, revision: str, *, batch_index: int, input_hash: str, response: dict[str, Any]
    ) -> None:
        with self.db.connect() as connection:
            connection.execute(
                """
                INSERT INTO assistant_source_card_batches(
                    revision, batch_index, input_hash, card_json, created_at
                ) VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(revision, batch_index) DO UPDATE SET
                    input_hash=excluded.input_hash, card_json=excluded.card_json
                """,
                (revision, batch_index, input_hash, json.dumps(response, ensure_ascii=False), utc_now()),
            )

    def _merge_card_batches(self, revision: str) -> dict[str, Any]:
        with self.db.connect() as connection:
            rows = connection.execute(
                "SELECT card_json FROM assistant_source_card_batches WHERE revision=? ORDER BY batch_index",
                (revision,),
            ).fetchall()
        cards = [json.loads(row["card_json"]) for row in rows]
        return {
            "summary": "\n\n".join(
                str(card.get("summary") or "").strip() for card in cards
                if str(card.get("summary") or "").strip()
            )[:3000],
            "key_points": [
                point for card in cards for point in (card.get("key_points") or [])
            ][:8],
            "topics": list(dict.fromkeys(
                str(topic).strip() for card in cards for topic in (card.get("topics") or [])
                if str(topic).strip()
            ))[:5],
            "limitations": list(dict.fromkeys(
                str(item).strip() for card in cards for item in (card.get("limitations") or [])
                if str(item).strip()
            ))[:5],
        }

    def _find_page(self, space_id: int, title: str) -> dict[str, Any] | None:
        normalized = self._normalize_title(title)
        with self.db.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM assistant_wiki_pages
                WHERE principal_id=? AND space_id=? AND normalized_title=? AND status='active'
                """,
                (self.principal_id, space_id, normalized),
            ).fetchone()
        return self._decode_page(dict(row)) if row else None

    def _find_related_page(self, space_id: int, card: dict[str, Any]) -> dict[str, Any] | None:
        topics = [str(value).strip() for value in card.get("topics", []) if str(value).strip()]
        if not topics:
            return None
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM assistant_wiki_pages
                WHERE principal_id=? AND space_id=? AND status='active'
                ORDER BY updated_at DESC
                """,
                (self.principal_id, space_id),
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
            token for token in shared
            if len(token) >= 4 and token.isascii()
            and token not in {"agent", "coding", "code", "project", "system", "interview"}
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
            token for token in re.findall(r"[a-z0-9]+", lowered)
            if len(token) >= 3 and token not in {"the", "and", "with", "from"}
        }
        chinese_runs = re.findall(r"[\u4e00-\u9fff]+", lowered)
        bigrams = {
            run[index:index + 2]
            for run in chinese_runs for index in range(max(0, len(run) - 1))
        }
        bigrams.difference_update({
            "来源", "视频", "材料", "内容", "整理", "相关", "可以", "适用",
            "需要", "当前", "通过", "一个", "一种", "以及", "没有", "进行",
        })
        return words.union(bigrams)

    @staticmethod
    def _scope(space: dict[str, Any]) -> SourceScope:
        return SourceScope(
            source_db_ids=frozenset(int(value) for value in space["source_ids"]),
            video_ids=frozenset(int(value) for value in space.get("video_ids", [])),
            all_active=bool(space["all_active"]),
        )

    @staticmethod
    def _ensure_dirty(connection: Any, video_id: int) -> int:
        row = connection.execute(
            "SELECT dirty_generation FROM assistant_source_dirty WHERE video_id=?", (video_id,)
        ).fetchone()
        if row is None:
            connection.execute(
                "INSERT INTO assistant_source_dirty(video_id, dirty_generation, updated_at) VALUES(?, 1, ?)",
                (video_id, utc_now()),
            )
            return 1
        return int(row["dirty_generation"])

    def _enqueue_reconcile(self, connection: Any, video_id: int, generation: int,
                           *, batch_id: str | None = None) -> str:
        return self.store.enqueue_job(
            connection,
            kind="source_reconcile",
            dedupe_key=f"source_reconcile:{video_id}:{generation}" + (f":batch:{batch_id}" if batch_id else ""),
            payload={"video_id": video_id, "dirty_generation": generation,
                     **({"maintenance_batch_id": batch_id} if batch_id else {})},
        )

    def _budgeted_provider(self, payload: dict[str, Any], provider: StructuredProvider) -> StructuredProvider:
        batch_id = payload.get("maintenance_batch_id")
        return BudgetedStructuredProvider(
            self.store, str(batch_id) if batch_id else None, provider
        )

    @staticmethod
    def _card_material(snapshot: dict[str, Any]) -> tuple[str, str]:
        materials = snapshot["materials"]
        selected = next(
            ((kind, str(materials[kind])) for kind in ("summary", "raw_subtitle", "transcript")
             if materials.get(kind)), None
        )
        notes = "\n\n".join(
            f"[已有注释 id={item['id']}；作者身份未核实；更新于 {item.get('updated_at') or '未知'}]\n{item['content']}"
            for item in snapshot.get("notes", []) if str(item.get("content") or "").strip()
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
            f"{selected[0]}_and_notes" if selected and notes else
            selected[0] if selected else "metadata_and_notes"
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
        old_identity = {key: value for key, value in old.get("metadata", {}).items()
                        if key not in time_fields}
        new_identity = {key: value for key, value in new.get("metadata", {}).items()
                        if key not in time_fields}
        if old_identity != new_identity:
            return False
        if old.get("metadata", {}).get("published_at") != new.get("metadata", {}).get("published_at"):
            body = json.dumps({"summary": old_card.get("summary"),
                               "key_points": old_card.get("key_points")}, ensure_ascii=False)
            if re.search(r"\b(?:19|20)\d{2}\b", body):
                return False
        return True

    @classmethod
    def _normalize_card(
        cls, response: dict[str, Any], snapshot: dict[str, Any], material_kind: str
    ) -> dict[str, Any]:
        points = []
        material, material_kind_actual = cls._card_material(snapshot)
        note_content = "\n".join(str(note.get("content") or "") for note in snapshot.get("notes", []))
        for item in response.get("key_points", [])[:8]:
            if not isinstance(item, dict) or not str(item.get("markdown") or "").strip():
                continue
            assessment = str(item.get("assessment") or "source_reported")
            quote = str(item.get("evidence_quote") or "").strip()[:500]
            position = material.find(quote) if quote else -1
            if assessment == "user_annotation" and (not quote or quote not in note_content):
                assessment = "source_reported"
            cited_source = str(item.get("cited_source") or "").strip()[:200]
            if (cited_source and cited_source not in material) or not cls._reference_like(cited_source) or re.search(
                r"视频章节|视频简介|视频字幕|\d{2}:\d{2}:\d{2}", cited_source
            ):
                cited_source = ""
            points.append({
                "heading": str(item.get("heading") or "关键观点")[:120],
                "markdown": str(item["markdown"]).strip()[:6000],
                "applicability": str(item.get("applicability") or "")[:500],
                "assessment": assessment if assessment in {"source_reported", "user_annotation"} else "source_reported",
                "evidence_quote": quote if position >= 0 else "",
                "position": {"start": position, "end": position + len(quote)} if position >= 0 else None,
                "material_view": material_kind_actual,
                "speaker": "",  # A video's uploader does not establish who speaks.
                "cited_source": cited_source if position >= 0 else "",
                "cited_source_checked": False,
            })
        metadata = snapshot["metadata"]
        return {
            "title": str(metadata.get("title") or "未命名材料"),
            "uploader": str(metadata.get("uploader") or ""),
            "published_at": metadata.get("published_at"),
            "memberships": snapshot["memberships"],
            "coverage": snapshot["coverage"],
            "material_kind": material_kind,
            "material_views": [kind for kind in ("summary", "raw_subtitle", "transcript")
                               if snapshot["materials"].get(kind)],
            "annotation_count": len(snapshot.get("notes", [])),
            "metadata_observed_at": metadata.get("metadata_observed_at"),
            "summary": str(response.get("summary") or "").strip()[:3000],
            "key_points": points,
            "topics": [str(value).strip()[:120] for value in response.get("topics", [])[:5] if str(value).strip()],
            "limitations": [str(value).strip()[:500] for value in response.get("limitations", [])[:5] if str(value).strip()],
        }

    @classmethod
    def _normalize_wiki_patch(
        cls, response: dict[str, Any], *, topic: str, card: dict[str, Any], revision: str,
        source_key_map: dict[str, str] | None = None,
        source_titles: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        page_type = str(response.get("page_type") or "topic")
        if page_type not in {"concept", "method", "comparison", "topic"}:
            page_type = "topic"
        def public_text(value: Any, limit: int) -> str:
            clean = str(value or "").strip()[:limit]
            for key, title in (source_titles or {}).items():
                clean = re.sub(rf"(?<![A-Za-z0-9]){re.escape(key)}(?![A-Za-z0-9])",
                               f"《{title[:80]}》", clean)
            clean = re.sub(r"key=(《[^》]+》)", r"\1", clean)
            clean = re.sub(r"coverage=[a-z_]+", "当前可用材料", clean)
            clean = re.sub(r"material_kind=[a-z_]+", "摘要材料视图", clean)
            return clean
        blocks = []
        all_keyed = True
        for item in response.get("blocks", [])[:5]:
            if not isinstance(item, dict) or not str(item.get("markdown") or "").strip():
                continue
            keys = item.get("source_keys")
            if source_key_map and isinstance(keys, list):
                if not keys or any(str(key) not in source_key_map for key in keys):
                    continue
                source_revisions = list(dict.fromkeys(source_key_map[str(key)] for key in keys))
            else:
                all_keyed = False
                source_revisions = [revision]
            quote = str(item.get("evidence_quote") or "").strip()[:500]
            supporting_point = next(
                (point for point in card.get("key_points", [])
                 if quote and point.get("evidence_quote") == quote), None
            )
            assessment = str(item.get("assessment") or "source_reported")
            if assessment == "user_annotation" and (
                supporting_point is None or supporting_point.get("assessment") != "user_annotation"
            ):
                assessment = "source_reported"
            if assessment not in {"source_reported", "user_annotation"}:
                assessment = "system_synthesis"
            blocks.append({
                "heading": public_text(item.get("heading") or card["title"], 120),
                "markdown": public_text(item["markdown"], 12000),
                "applicability": public_text(item.get("applicability"), 500),
                "assessment": assessment,
                "relation": public_text(item.get("relation") or "related", 100),
                "speaker": "",
                "cited_source": (
                    str(supporting_point.get("cited_source") or "")
                    if supporting_point and cls._reference_like(
                        str(supporting_point.get("cited_source") or "")
                    ) else ""
                ),
                "evidence_quote": quote if supporting_point else "",
                "material_view": str(supporting_point.get("material_view") or card.get("material_kind") or "") if supporting_point else str(card.get("material_kind") or ""),
                "position": supporting_point.get("position") if supporting_point else None,
                "source_refs": source_revisions,
            })
        return {
            "title": str(response.get("title") or topic).strip()[:200],
            "page_type": page_type,
            "summary": public_text(response.get("summary") or card.get("summary"), 3000),
            "blocks": blocks,
            "replace_derived": bool(blocks and all_keyed),
            "source_title": card["title"],
            "revision": revision,
        }

    @classmethod
    def _blocks_with_identity(cls, blocks: list[dict[str, Any]], *, revision: str, topic: str) -> list[dict[str, Any]]:
        values = []
        for index, block in enumerate(blocks):
            source_refs = list(dict.fromkeys(str(value) for value in
                                             block.get("source_refs", [revision])))
            stable = hashlib.sha256(
                f"{topic}:{cls.COMPILER_VERSION}:{index}:{','.join(sorted(source_refs))}".encode("utf-8")
            ).hexdigest()[:20]
            values.append({
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
            })
        return values

    @staticmethod
    def _page_for_prompt(
        page: dict[str, Any] | None, *, source_key_map: dict[str, str] | None = None
    ) -> dict[str, Any] | None:
        if page is None:
            return None
        revision_keys = {revision: key for key, revision in (source_key_map or {}).items()}
        return {
            "title": page["title"], "summary": page["summary"], "version": page["version"],
            "availability": page.get("availability", "full"),
            "blocks": [{
                "heading": block["heading"], "markdown": block["markdown"][:1500],
                "manual_lock": bool(block.get("manual_lock")),
                "assessment": block.get("assessment") or "source_reported",
                "content_origin": "personal_note" if block.get("assessment") == "user_explicit" else "source",
                "source_keys": [revision_keys[ref] for ref in block.get("source_refs", [])
                                if ref in revision_keys],
            } for block in page["blocks"][-8:]],
        }

    @staticmethod
    def _normalize_title(value: str) -> str:
        return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.casefold())[:200]

    @staticmethod
    def _decode_page(value: dict[str, Any]) -> dict[str, Any]:
        value["aliases"] = json.loads(value.pop("aliases_json"))
        value["blocks"] = json.loads(value.pop("blocks_json"))
        return value

    @staticmethod
    def _fts_replace(connection: Any, page: dict[str, Any]) -> None:
        connection.execute("DELETE FROM assistant_wiki_fts WHERE page_id=?", (page["id"],))
        connection.execute(
            "INSERT INTO assistant_wiki_fts(page_id,title,aliases,summary,blocks) VALUES(?,?,?,?,?)",
            (
                page["id"], page["title"], " ".join(page["aliases"]), page["summary"],
                "\n".join(f"{block['heading']} {block['markdown']}" for block in page["blocks"]),
            ),
        )
