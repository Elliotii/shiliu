from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shiliu.domain import PipelineError
from shiliu.llm import OpenAICompatibleProvider
from shiliu.taxonomy.model_calls import AuditedJsonCaller
from shiliu.taxonomy.repository import TaxonomyRepository


COMPACT_VIEW_VERSION = "compact-discovery-view-v1"
LOCAL_DISCOVERY_PROMPT_VERSION = "batched-local-discovery-v3"
CONSOLIDATION_PROMPT_VERSION = "global-consolidation-v3"
ASSIGNMENT_PROMPT_VERSION = "batched-trial-assignment-v1"
CONTENT_TYPE_RECOVERY_PROMPT_VERSION = "content-type-recovery-v1"


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Some OpenAI-compatible models add harmless local IDs to Topic/Entity
    # candidates even when the prompt forbids them. Accept and discard those
    # IDs so JSON Repair need not rewrite an otherwise valid response. They
    # never enter consolidation or the stable Domain tree.
    provisional_id: str | None = Field(
        default=None,
        pattern=r"^l(?:t|e)_[a-z0-9_]+$",
        exclude=True,
    )
    name: str = Field(min_length=1, max_length=80)
    definition: str = Field(min_length=1, max_length=240)
    supporting_ids: list[str] = Field(min_length=1, max_length=32)


class ContentTypeCandidate(Candidate):
    provisional_id: str = Field(pattern=r"^lct_[a-z0-9_]+$")
    includes: list[str] = Field(min_length=1, max_length=8)
    excludes: list[str] = Field(min_length=1, max_length=8)


class EntityCandidate(Candidate):
    entity_type: Literal[
        "model", "tool", "project", "framework", "paper", "person",
        "organization", "concept", "unknown",
    ]


class DomainCandidate(Candidate):
    provisional_id: str = Field(pattern=r"^ld_[a-z0-9_]+$")
    includes: list[str] = Field(min_length=1, max_length=8)
    excludes: list[str] = Field(min_length=1, max_length=8)
    suggested_level: Literal["primary", "subdomain"]
    parent_hint: str | None = Field(default=None, max_length=80)
    stability_reason: str = Field(min_length=1, max_length=240)


class LocalDiscoveryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_types: list[ContentTypeCandidate] = Field(default_factory=list, max_length=12)
    domains: list[DomainCandidate] = Field(default_factory=list, max_length=16)
    topics: list[Candidate] = Field(default_factory=list, max_length=20)
    entities: list[EntityCandidate] = Field(default_factory=list, max_length=30)
    ambiguous_ids: list[str] = Field(default_factory=list)


class ContentTypeRecoveryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_types: list[ContentTypeCandidate] = Field(min_length=1, max_length=12)


class DraftNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    definition: str
    includes: list[str] = Field(min_length=1)
    excludes: list[str] = Field(min_length=1)
    supporting_ids: list[str] = Field(min_length=1)
    representative_ids: list[str] = Field(min_length=1)
    parent_id: str | None
    node_type: Literal["content_type", "domain"]
    # Models often emit `children: []` on leaf nodes. Accept only the empty
    # compatibility form and discard it; non-empty third-level nodes remain
    # invalid because this list cannot contain any values.
    children: list[None] = Field(default_factory=list, max_length=0, exclude=True)


class DraftDomainNode(DraftNode):
    children: list[DraftNode] = Field(default_factory=list, max_length=6)


class ConsolidatedDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_types: list[DraftNode]
    domains: list[DraftDomainNode]
    topics: list[Candidate]
    entities: list[EntityCandidate]
    consolidation_notes: list[str]

    @model_validator(mode="before")
    @classmethod
    def discard_unsupported_topics_and_entities(cls, value):
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        for key in ("topics", "entities"):
            candidates = normalized.get(key)
            if isinstance(candidates, list):
                normalized[key] = [
                    item
                    for item in candidates
                    if not isinstance(item, dict) or item.get("supporting_ids")
                ]
        return normalized


class TrialAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_id: str
    content_type_ids: list[str]
    primary_domain_path: list[str] = Field(max_length=2)
    secondary_domain_ids: list[str]
    dynamic_topics: list[str]
    entities: list[str]
    certainty: Literal["high", "medium", "low"]
    rejection_reason: Literal[
        "insufficient_evidence", "out_of_scope", "cross_domain", "taxonomy_gap"
    ] | None


class TrialAssignmentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignments: list[TrialAssignment]


class BatchedDiscoverySpikeService:
    """Experimental batch discovery; it does not mutate production taxonomy state."""

    def __init__(
        self,
        *,
        repository: TaxonomyRepository,
        provider_factory,
        output_dir: Path,
    ) -> None:
        self.repository = repository
        self.provider_factory = provider_factory
        self.output_dir = output_dir

    def run_spike(
        self,
        snapshot_id: int,
        *,
        batch_size: int = 24,
        seed: int = 73,
        limit: int | None = None,
        include_assignment: bool = True,
    ) -> dict[str, Any]:
        if not 20 <= batch_size <= 32:
            raise ValueError("Discovery batch_size must be between 20 and 32")
        snapshot = self.repository.get_snapshot(snapshot_id)
        if snapshot is None:
            raise LookupError("快照不存在")
        compact = build_compact_corpus(snapshot["cards"])
        eligible = [row for row in compact["rows"] if row[1] != "D"]
        rng = random.Random(seed)
        rng.shuffle(eligible)
        if limit is not None:
            if limit < 20:
                raise ValueError("Discovery Spike limit must be at least 20")
            eligible = eligible[:limit]

        run_id = (
            f"discovery-spike-s{snapshot_id}-"
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        )
        run_dir = self.output_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        _write_json(run_dir / "short-id-map.json", compact["id_map"])
        _write_json(run_dir / "compact-corpus.json", compact)
        manifest_path = run_dir / "manifest.json"
        manifest: dict[str, Any] = {
            "run_id": run_id,
            "kind": "batched_discovery_spike",
            "production_stage": False,
            "snapshot_id": snapshot_id,
            "snapshot_hash": snapshot["snapshot_hash"],
            "compact_view_version": COMPACT_VIEW_VERSION,
            "batch_size": batch_size,
            "seed": seed,
            "eligible_count": len(eligible),
            "trial_only_count": sum(row[1] == "D" for row in compact["rows"]),
            "status": "running_local_discovery",
            "local_calls": [],
            "consolidation_call": None,
            "assignment_calls": [],
            "created_at": _utc_now(),
        }
        _write_json(manifest_path, manifest)

        local_provider = self.provider_factory("taxonomy_local")
        repair_provider = self.provider_factory("taxonomy_repair")
        caller = AuditedJsonCaller(
            provider=local_provider, repair_provider=repair_provider
        )
        batches = [
            eligible[index:index + batch_size]
            for index in range(0, len(eligible), batch_size)
        ]
        local_outputs: list[LocalDiscoveryOutput] = []
        for index, batch in enumerate(batches, start=1):
            prompt = build_local_discovery_prompt(batch)
            try:
                result, audit = caller.call(
                    call_dir=run_dir / f"local-{index:02d}",
                    prompt=prompt,
                    prompt_version=LOCAL_DISCOVERY_PROMPT_VERSION,
                    schema=LocalDiscoveryOutput,
                    schema_hint=LOCAL_SCHEMA_HINT,
                    max_tokens=8192,
                    input_ids=[row[0] for row in batch],
                    validator=lambda value, allowed={row[0] for row in batch}: (
                        _validate_local_output(value, allowed)
                    ),
                )
            except PipelineError as exc:
                _mark_failed(manifest, manifest_path, "local_discovery", f"local-{index:02d}", exc)
                raise
            local_outputs.append(result)
            manifest["local_calls"].append(_manifest_call(audit, f"local-{index:02d}"))
            _write_json(manifest_path, manifest)

        candidates = [value.model_dump(mode="json") for value in local_outputs]
        _write_json(run_dir / "local-candidates.json", candidates)
        manifest["status"] = "consolidating"
        _write_json(manifest_path, manifest)
        global_provider = self.provider_factory("taxonomy_global")
        global_caller = AuditedJsonCaller(
            provider=global_provider, repair_provider=repair_provider
        )
        consolidation_prompt = build_consolidation_prompt(candidates)
        try:
            draft, audit = global_caller.call(
                call_dir=run_dir / "consolidation",
                prompt=consolidation_prompt,
                prompt_version=CONSOLIDATION_PROMPT_VERSION,
                schema=ConsolidatedDraft,
                schema_hint=CONSOLIDATION_SCHEMA_HINT,
                max_tokens=16384,
                input_ids=sorted(
                    {
                        short_id
                        for batch in local_outputs
                        for group in (batch.content_types, batch.domains, batch.topics, batch.entities)
                        for item in group
                        for short_id in item.supporting_ids
                    }
                ),
                validator=lambda value: _validate_draft(value, set(compact["id_map"])),
            )
        except PipelineError as exc:
            _mark_failed(manifest, manifest_path, "consolidation", "consolidation", exc)
            raise
        draft_payload = draft.model_dump(mode="json")
        _write_json(run_dir / "taxonomy-draft.json", draft_payload)
        manifest["consolidation_call"] = _manifest_call(audit, "consolidation")

        assignments: list[TrialAssignment] = []
        if include_assignment:
            manifest["status"] = "trial_assigning"
            _write_json(manifest_path, manifest)
            selected_ids = {item[0] for item in eligible}
            assignment_rows = [
                row
                for row in compact["rows"]
                if limit is None or row[0] in selected_ids or row[1] == "D"
            ]
            assignment_provider = self.provider_factory("taxonomy_assignment")
            assignment_caller = AuditedJsonCaller(
                provider=assignment_provider, repair_provider=repair_provider
            )
            assignment_batches = [
                assignment_rows[index:index + batch_size]
                for index in range(0, len(assignment_rows), batch_size)
            ]
            for index, batch in enumerate(assignment_batches, start=1):
                prompt = build_assignment_prompt(draft_payload, batch)
                try:
                    result, assignment_audit = assignment_caller.call(
                        call_dir=run_dir / f"assignment-{index:02d}",
                        prompt=prompt,
                        prompt_version=ASSIGNMENT_PROMPT_VERSION,
                        schema=TrialAssignmentOutput,
                        schema_hint=ASSIGNMENT_SCHEMA_HINT,
                        max_tokens=12288,
                        input_ids=[row[0] for row in batch],
                        validator=lambda value, expected={row[0] for row in batch}: (
                            _validate_assignments(value, expected, draft)
                        ),
                    )
                except PipelineError as exc:
                    _mark_failed(
                        manifest, manifest_path, "trial_assignment", f"assignment-{index:02d}", exc
                    )
                    raise
                assignments.extend(result.assignments)
                manifest["assignment_calls"].append(
                    _manifest_call(assignment_audit, f"assignment-{index:02d}")
                )
                _write_json(manifest_path, manifest)

        assignment_payload = [
            {
                **item.model_dump(mode="json"),
                "content_key": compact["id_map"][item.content_id],
            }
            for item in assignments
        ]
        _write_json(run_dir / "trial-assignments.json", assignment_payload)
        novelty = [
            item for item in assignment_payload
            if item["certainty"] == "low"
            or item["rejection_reason"] is not None
        ]
        _write_json(run_dir / "novelty-pool.json", novelty)
        manifest.update(
            status="completed",
            completed_at=_utc_now(),
            draft_hash=_stable_hash(draft_payload),
            assignment_count=len(assignments),
            novelty_pool_count=len(novelty),
            totals=_call_totals(manifest),
        )
        _write_json(manifest_path, manifest)
        return {**manifest, "run_dir": str(run_dir)}


def build_compact_corpus(cards: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a frozen-card projection without changing the stored Snapshot rows."""

    rows: list[list[Any]] = []
    id_map: dict[str, str] = {}
    reverse_id_map: dict[str, str] = {}
    for index, card in enumerate(cards, start=1):
        short_id = f"C{index:03d}"
        content_key = str(card["content_key"])
        id_map[short_id] = content_key
        reverse_id_map[content_key] = short_id
        view = card["discovery_view"]
        evidence = str(card["evidence_level"])
        title = _clean_text(view.get("title"), 240)
        if evidence in {"A", "B"}:
            points = _dedupe_texts(view.get("key_points") or [], limit=3, max_chars=220)
            entities = _dedupe_texts(
                view.get("projects_tools_models") or [], limit=5, max_chars=100
            )
            rows.append(
                [
                    short_id,
                    evidence,
                    title,
                    _clean_text(view.get("one_line_summary"), 360),
                    points,
                    entities,
                ]
            )
        elif evidence == "C":
            rows.append(
                [short_id, evidence, title, _clean_text(view.get("description"), 300)]
            )
        else:
            rows.append([short_id, "D", title])
    return {
        "version": COMPACT_VIEW_VERSION,
        "row_protocol": {
            "A_or_B": ["short_id", "evidence", "title", "conclusion", "key_points", "entities"],
            "C": ["short_id", "evidence", "title", "description"],
            "D": ["short_id", "evidence", "title"],
        },
        "rows": rows,
        "id_map": id_map,
        "reverse_id_map": reverse_id_map,
    }


def build_local_discovery_prompt(rows: list[list[Any]]) -> str:
    return f"""你是局部候选发现器，不生成最终 Taxonomy。只依据本批卡片发现候选。
严格分离稳定 Domain、动态 Topic、具体 Entity 和 Content Type；项目、工具、模型、论文、人物不得成为 Domain。
Content Type 回答“内容采用什么表达或使用形式”，不是“内容讨论什么知识领域”。必须独立检查本批是否存在教程、评测、经验、观点、项目演示等表达形式，但名称必须依据本批自行生成。
Content Type 和 Domain 候选都要写包含边界、排除边界和本批 supporting_ids；局部 provisional_id 只在本批内唯一。
Domain 候选标记 suggested_level=primary|subdomain。subdomain 是可长期复用、边界清晰的稳定知识细分；Dynamic Topic 是阶段性专题、具体做法或短期概念。二级候选不要求跨批出现，但必须有真实语料支持并填写 parent_hint 和 stability_reason。
不要只输出宽泛一级领域，也不要为凑数制造二级领域。不能推测本批以外的覆盖率。
ambiguous_ids 记录证据不足或局部无法判断的内容。只输出 JSON。

精简输出结构：{LOCAL_SCHEMA_HINT}
输入行协议：A/B=[id,等级,标题,一句话结论,最多3条观点,最多5个实体]；C=[id,C,标题,最多300字简介]。
本批卡片：
{_rows_text(rows)}"""


def build_content_type_recovery_prompt(rows: list[list[Any]]) -> str:
    return f"""你只恢复局部 Discovery 缺失的 Content Type 维度，不得生成或修改 Domain、Topic、Entity。
Content Type 回答“内容采用什么表达或使用形式”，不是知识领域。依据本批卡片发现可复用的表达形式，输出名称、定义、包含边界、排除边界和 supporting IDs。
局部 provisional_id 使用 lct_ 前缀且本批唯一。每个 supporting ID 必须来自本批。只输出 JSON。

精简输出结构：{CONTENT_TYPE_RECOVERY_SCHEMA_HINT}
本批卡片：
{_rows_text(rows)}"""


def build_consolidation_prompt(candidates: list[dict[str, Any]]) -> str:
    support_counts = _candidate_support_summary(candidates)
    return f"""你是全局候选归并器。输入只有各批局部候选，不包含原始视频卡片。
归并语义相同但名称不同的候选，严格分离 Content Type、稳定 Domain、动态 Topic 和 Entity。
建立最多两级 Domain 树；一级建议5至10个，不必为每个一级领域生成子领域。
二级领域综合语料支持、语义边界、长期复用价值、浏览价值和父子关系判断；跨批出现是稳定信号，但不是硬性必要条件。
节点 ID 使用 ct_、d_ 前缀并全局唯一。每个稳定节点必须输出 includes、excludes、supporting_ids、representative_ids、parent_id 和 node_type。
representative_ids 必须来自 supporting_ids；supporting_ids 只能使用输入出现过的短 ID。
只有 Content Type 和 Domain 节点带 id；topics 与 entities 严禁增加 id 字段。
不得把项目、工具、模型、论文、人物、短期术语放入 Domain 树。只输出 JSON。

精简输出结构：{CONSOLIDATION_SCHEMA_HINT}
候选支持统计：{_compact_json(support_counts)}
局部候选：{_compact_json(candidates)}"""


def build_assignment_prompt(draft: dict[str, Any], rows: list[list[Any]]) -> str:
    return f"""你是冻结 Taxonomy 的试分类器。不得新建、重命名、移动或修改节点。
逐条选择 Content Type 和最多两级 primary_domain_path；必要时给 secondary_domain_ids、动态 Topic 和 Entity。
D 级只有标题，不得强制高确定度分类，允许 insufficient_evidence。
无法匹配时使用 out_of_scope、cross_domain 或 taxonomy_gap。每个输入 ID 必须且只能输出一次。只输出 JSON。

精简输出结构：{ASSIGNMENT_SCHEMA_HINT}
冻结 Taxonomy：{_compact_json(draft)}
卡片行：
{_rows_text(rows)}"""


LOCAL_SCHEMA_HINT = (
    '{"content_types":[{"provisional_id":"lct_x","name":"","definition":"",'
    '"includes":[""],"excludes":[""],"supporting_ids":["C001"]}],'
    '"domains":[{"provisional_id":"ld_x","name":"","definition":"",'
    '"includes":[""],"excludes":[""],"supporting_ids":["C001"],'
    '"suggested_level":"primary|subdomain","parent_hint":null|"父级概念",'
    '"stability_reason":"长期复用依据"}],'
    '"topics":[候选结构],'
    '"entities":[{"name":"","definition":"","supporting_ids":["C001"],'
    '"entity_type":"model|tool|project|framework|paper|person|organization|concept|unknown"}],'
    '"ambiguous_ids":["C002"]}'
)
CONTENT_TYPE_RECOVERY_SCHEMA_HINT = (
    '{"content_types":[{"provisional_id":"lct_x","name":"","definition":"",'
    '"includes":[""],"excludes":[""],"supporting_ids":["C001"]}]}'
)
CONSOLIDATION_SCHEMA_HINT = (
    '{"content_types":[{"id":"ct_01","name":"","definition":"","includes":[""],'
    '"excludes":[""],"supporting_ids":["C001"],"representative_ids":["C001"],'
    '"parent_id":null,"node_type":"content_type"}],'
    '"domains":[{"id":"d_01","name":"","definition":"","includes":[""],'
    '"excludes":[""],"supporting_ids":["C001"],"representative_ids":["C001"],'
    '"parent_id":null,"node_type":"domain","children":['
    '{"id":"d_01_01","name":"","definition":"","includes":[""],"excludes":[""],'
    '"supporting_ids":["C001"],"representative_ids":["C001"],'
    '"parent_id":"d_01","node_type":"domain"}]}],'
    '"topics":[候选结构],"entities":[实体候选结构],"consolidation_notes":[""]}'
)
ASSIGNMENT_SCHEMA_HINT = (
    '{"assignments":[{"content_id":"C001","content_type_ids":[],"primary_domain_path":[],'
    '"secondary_domain_ids":[],"dynamic_topics":[],"entities":[],'
    '"certainty":"high|medium|low","rejection_reason":null|'
    '"insufficient_evidence|out_of_scope|cross_domain|taxonomy_gap"}]}'
)


def _validate_local_output(value: LocalDiscoveryOutput, allowed: set[str]) -> None:
    used = set(value.ambiguous_ids)
    for group in (value.content_types, value.domains, value.topics, value.entities):
        for candidate in group:
            used.update(candidate.supporting_ids)
    if not used <= allowed:
        raise PipelineError(
            "局部候选引用了本批之外的短 ID", code="local_candidate_id_mismatch", retryable=False
        )


def _validate_draft(value: ConsolidatedDraft, allowed: set[str]) -> None:
    ids = [item.id for item in value.content_types]
    for parent in value.domains:
        ids.append(parent.id)
        ids.extend(child.id for child in parent.children)
    if len(ids) != len(set(ids)):
        raise PipelineError("Draft 节点 ID 不唯一", code="draft_id_collision", retryable=False)
    supports: set[str] = set()
    for item in value.content_types:
        supports.update(item.supporting_ids)
    for parent in value.domains:
        supports.update(parent.supporting_ids)
        for child in parent.children:
            supports.update(child.supporting_ids)
    if not supports <= allowed:
        raise PipelineError("Draft 引用了未知短 ID", code="draft_support_mismatch", retryable=False)


def _validate_assignments(
    value: TrialAssignmentOutput, expected: set[str], draft: ConsolidatedDraft
) -> None:
    actual = [item.content_id for item in value.assignments]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise PipelineError(
            "Trial Assignment 未逐一覆盖本批内容", code="assignment_id_mismatch", retryable=False
        )
    content_types = {item.id for item in draft.content_types}
    domain_ids = {item.id for item in draft.domains}
    domain_ids.update(child.id for item in draft.domains for child in item.children)
    for item in value.assignments:
        if not set(item.content_type_ids) <= content_types:
            raise PipelineError("Assignment 引用了未知 Content Type", code="assignment_node_mismatch", retryable=False)
        if not set(item.primary_domain_path + item.secondary_domain_ids) <= domain_ids:
            raise PipelineError("Assignment 引用了未知 Domain", code="assignment_node_mismatch", retryable=False)


def _candidate_support_summary(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        kind: [
            {"name": item["name"], "support_count": len(set(item["supporting_ids"]))}
            for batch in candidates
            for item in batch[kind]
        ]
        for kind in ("content_types", "domains", "topics", "entities")
    }


def _manifest_call(audit: dict[str, Any], directory: str) -> dict[str, Any]:
    return {
        "directory": directory,
        "status": audit["status"],
        "model": audit["model"],
        "input_count": audit["input_count"],
        "input_chars": audit["input_chars"],
        "elapsed_seconds": audit.get("elapsed_seconds"),
        "usage": audit.get("usage"),
        "repair": audit.get("repair"),
    }


def _call_totals(manifest: dict[str, Any]) -> dict[str, Any]:
    calls = list(manifest["local_calls"]) + list(manifest["assignment_calls"])
    if manifest.get("consolidation_call"):
        calls.append(manifest["consolidation_call"])
    usage_sources = [
        usage
        for call in calls
        for usage in (
            call.get("usage"),
            (call.get("repair") or {}).get("usage"),
        )
        if usage
    ]
    usage_keys = {
        key
        for usage in usage_sources
        for key, value in usage.items()
        if isinstance(value, (int, float))
    }
    usage = {
        key: sum(value for source in usage_sources if isinstance((value := source.get(key)), (int, float)))
        for key in usage_keys
    }
    return {
        "logical_calls": len(calls),
        "actual_requests": len(calls) + sum(call.get("repair") is not None for call in calls),
        "input_chars": sum(
            call["input_chars"] + ((call.get("repair") or {}).get("input_chars") or 0)
            for call in calls
        ),
        "elapsed_seconds": round(
            sum(
                (call.get("elapsed_seconds") or 0)
                + ((call.get("repair") or {}).get("elapsed_seconds") or 0)
                for call in calls
            ),
            3,
        ),
        "usage": usage or None,
        "repair_calls": sum(call.get("repair") is not None for call in calls),
    }


def _dedupe_texts(values: list[Any], *, limit: int, max_chars: int) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_text(value, max_chars)
        key = "".join(text.lower().split())
        if text and key not in seen:
            seen.add(key)
            output.append(text)
        if len(output) == limit:
            break
    return output


def _clean_text(value: Any, max_chars: int) -> str:
    return " ".join(str(value or "").split())[:max_chars]


def _rows_text(rows: list[list[Any]]) -> str:
    return "\n".join(_compact_json(row) for row in rows)


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _mark_failed(
    manifest: dict[str, Any],
    manifest_path: Path,
    stage: str,
    call: str,
    error: PipelineError,
) -> None:
    manifest.update(
        status="failed",
        failed_stage=stage,
        failed_call=call,
        error_code=error.code,
        error_message=str(error),
        failed_at=_utc_now(),
    )
    _write_json(manifest_path, manifest)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
