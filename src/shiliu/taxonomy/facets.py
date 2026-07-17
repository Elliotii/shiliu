from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shiliu.domain import PipelineError
from shiliu.llm import OpenAICompatibleProvider
from shiliu.taxonomy.domain import FacetBatchOutput, FacetOutput
from shiliu.taxonomy.repository import TaxonomyRepository


FACET_PROMPT_VERSION = "facet-extraction-v2"
ProviderFactory = Callable[[str], OpenAICompatibleProvider]


class FacetExtractionService:
    """Small, auditable Facet Spike runner over an immutable Snapshot."""

    def __init__(
        self,
        *,
        repository: TaxonomyRepository,
        provider_factory: ProviderFactory,
        output_dir: Path,
    ) -> None:
        self.repository = repository
        self.provider_factory = provider_factory
        self.output_dir = output_dir

    def run_spike(
        self,
        snapshot_id: int,
        *,
        limit: int = 12,
        seed: int = 42,
        batch_size: int = 4,
    ) -> dict[str, Any]:
        if not 10 <= limit <= 20:
            raise ValueError("Facet Spike limit must be between 10 and 20")
        if not 1 <= batch_size <= 5:
            raise ValueError("Facet Spike batch_size must be between 1 and 5")
        snapshot = self.repository.get_snapshot(snapshot_id)
        if snapshot is None:
            raise LookupError("快照不存在")
        cards = [card for card in snapshot["cards"] if card["discovery_eligible"]]
        selected = select_spike_cards(cards, limit=limit, seed=seed)
        if len(selected) < limit:
            raise ValueError("Discovery Eligible 卡片不足，无法运行指定规模的 Facet Spike")

        run_id = (
            f"facet-spike-s{snapshot_id}-"
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        )
        run_dir = self.output_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        provider = self.provider_factory("taxonomy_local")
        all_facets: list[FacetOutput] = []
        calls: list[dict[str, Any]] = []
        batches = [selected[index:index + batch_size] for index in range(0, len(selected), batch_size)]

        for call_index, batch in enumerate(batches, start=1):
            views = [card["discovery_view"] for card in batch]
            prompt = build_facet_prompt(views)
            input_hash = stable_hash({"prompt_version": FACET_PROMPT_VERSION, "views": views})
            call_path = run_dir / f"call-{call_index:02d}.json"
            audit: dict[str, Any] = {
                "call_index": call_index,
                "model": provider.model,
                "prompt_version": FACET_PROMPT_VERSION,
                "parameters": {
                    "thinking_enabled": provider.thinking_enabled,
                    "reasoning_effort": provider.reasoning_effort,
                    "max_tokens": 16384,
                    "batch_size": len(batch),
                },
                "input_content_ids": [view["content_id"] for view in views],
                "input_hash": input_hash,
                "output_path": call_path.name,
                "status": "running",
                "attempt_count": 0,
                "attempt_errors": [],
            }
            result: FacetBatchOutput | None = None
            last_error: PipelineError | None = None
            for attempt in range(1, 3):
                audit["attempt_count"] = attempt
                try:
                    candidate = provider.complete_json(
                        prompt,
                        FacetBatchOutput,
                        max_tokens=16384,
                    )
                    validate_batch(candidate, audit["input_content_ids"])
                    result = candidate
                    break
                except PipelineError as exc:
                    last_error = exc
                    audit["attempt_errors"].append(
                        {
                            "attempt": attempt,
                            "error_code": exc.code,
                            "error_message": str(exc),
                            "retryable": exc.retryable,
                        }
                    )
                    if not exc.retryable:
                        break
            if result is None:
                audit.update(
                    status="failed",
                    error_code=last_error.code if last_error else "facet_unknown",
                    error_message=str(last_error or "Facet extraction failed"),
                    output_hash=None,
                )
                write_json(call_path, {"audit": audit, "output": None})
                calls.append(audit)
                continue
            output = result.model_dump(mode="json")
            audit.update(status="completed", output_hash=stable_hash(output))
            write_json(call_path, {"audit": audit, "output": output})
            calls.append(audit)
            all_facets.extend(result.facets)

        facets_payload = [facet.model_dump(mode="json") for facet in all_facets]
        facets_path = run_dir / "facets.json"
        write_json(facets_path, facets_payload)
        manifest = {
            "run_id": run_id,
            "kind": "facet_spike",
            "production_stage": False,
            "snapshot_id": snapshot_id,
            "snapshot_hash": snapshot["snapshot_hash"],
            "prompt_version": FACET_PROMPT_VERSION,
            "model": provider.model,
            "seed": seed,
            "requested_count": limit,
            "completed_count": len(all_facets),
            "failed_batch_count": sum(call["status"] != "completed" for call in calls),
            "sample_evidence_counts": _evidence_counts(selected),
            "sample_content_ids": [card["content_key"] for card in selected],
            "calls": calls,
            "facets_path": facets_path.name,
            "facets_hash": stable_hash(facets_payload),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        write_json(run_dir / "manifest.json", manifest)
        return {**manifest, "run_dir": str(run_dir)}


def select_spike_cards(
    cards: list[dict[str, Any]], *, limit: int, seed: int
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    groups = {
        level: [card for card in cards if card["evidence_level"] == level]
        for level in ("A", "B", "C")
    }
    for values in groups.values():
        rng.shuffle(values)
    selected: list[dict[str, Any]] = []
    while len(selected) < limit and any(groups.values()):
        for level in ("A", "B", "C"):
            if groups[level] and len(selected) < limit:
                selected.append(groups[level].pop())
    rng.shuffle(selected)
    return selected


def build_facet_prompt(views: list[dict[str, Any]]) -> str:
    return f"""你是事实型语义抽取器，不是分类体系设计者。

任务：为每张内容卡提取多视角 Facet。输入顺序不代表重要性。

硬约束：
1. 只能依据卡片中已有的标题、简介、摘要、核心观点和实体提取事实。
2. 不得创建、建议或命名正式 Content Type、Domain、Subdomain 或 Taxonomy 节点。
3. main_subject 表示主要讨论对象；content_goal 表示内容希望帮助观看者完成什么。
4. technical_aspects 只写明确涉及的技术方面；usage_context 写学习、求职、开发等使用情境。
5. candidate_topics 只能是阶段性专题短语，不得声称它是稳定分类。
6. candidate_entities 中具体模型、工具、项目、框架、论文、人物和组织必须与抽象概念分开。
7. uploader 只是来源元数据；除非内容明确以该人物或组织为讨论对象，否则不得因为 uploader 字段把它加入 candidate_entities。
8. Harness、Skills、Memory、Workflow 等词在没有具体产品证据时标为 concept，不得猜成 tool 或 framework。
9. 证据不足时写入 ambiguity_notes，不得补充外部知识。
10. 每个输入 content_id 必须且只能输出一次，原样保留。
11. 只输出 JSON，不要 Markdown 或额外说明。

JSON 结构：
{{"facets":[{{
  "content_id":"原始 content_id",
  "main_subject":"主要讨论对象",
  "content_goal":"希望帮助观看者完成什么",
  "technical_aspects":["明确技术方面"],
  "usage_context":["使用情境"],
  "candidate_topics":["阶段性专题"],
  "candidate_entities":[{{"name":"实体名","entity_type":"model|tool|project|framework|paper|person|organization|concept|unknown","evidence":"卡片内依据"}}],
  "evidence_notes":["支持主要判断的卡片内证据"],
  "ambiguity_notes":["证据不足或歧义"]
}}]}}

内容卡 JSON：
{json.dumps(views, ensure_ascii=False, separators=(',', ':'))}
"""


def validate_batch(result: FacetBatchOutput, expected_ids: list[str]) -> None:
    actual = [facet.content_id for facet in result.facets]
    if len(actual) != len(set(actual)) or set(actual) != set(expected_ids):
        raise PipelineError(
            "Facet 输出没有逐一覆盖输入 content_id",
            code="facet_content_mismatch",
            retryable=True,
        )


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _evidence_counts(cards: list[dict[str, Any]]) -> dict[str, int]:
    return {
        level: sum(card["evidence_level"] == level for card in cards)
        for level in ("A", "B", "C", "D")
    }
