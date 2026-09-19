from __future__ import annotations

import hashlib
import json
import math
import random
import re
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shiliu.domain import PipelineError
from shiliu.llm import OpenAICompatibleProvider
from shiliu.taxonomy.discovery import build_compact_corpus
from shiliu.taxonomy.model_calls import AuditedJsonCaller
from shiliu.taxonomy.repository import TaxonomyRepository


PROFILE_VERSION = "classification_profile_v1"
PROFILE_PROMPT_VERSION = "classification-profile-generation-v2"
PROFILE_SCHEMA_HINT = (
    '{"profiles":[{"content_id":"C001","main_subject":"主要讨论对象",'
    '"content_goal":"信息不足","key_concepts":[],"usage_contexts":[],'
    '"entities":[],"unknown_terms":[],"source_evidence_level":"A|B|C"}]}'
)
ProviderFactory = Callable[[str], OpenAICompatibleProvider]
EvidenceLevel = Literal["A", "B", "C"]
Concept = Annotated[str, Field(min_length=1, max_length=60)]
Context = Annotated[str, Field(min_length=1, max_length=40)]
Entity = Annotated[str, Field(min_length=1, max_length=80)]
UnknownTerm = Annotated[str, Field(min_length=1, max_length=80)]


class ClassificationProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_id: str = Field(pattern=r"^C[0-9]{3,}$")
    main_subject: str = Field(min_length=1, max_length=80)
    content_goal: str = Field(min_length=1, max_length=120)
    key_concepts: list[Concept] = Field(default_factory=list, max_length=5)
    usage_contexts: list[Context] = Field(default_factory=list, max_length=3)
    entities: list[Entity] = Field(default_factory=list, max_length=5)
    unknown_terms: list[UnknownTerm] = Field(default_factory=list, max_length=3)
    source_evidence_level: EvidenceLevel

    @model_validator(mode="before")
    @classmethod
    def cap_bounded_fields(cls, value):
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        for key, limit in {"main_subject": 80, "content_goal": 120}.items():
            item = normalized.get(key)
            if isinstance(item, str):
                normalized[key] = item[:limit]
        for key, limit in {
            "key_concepts": 5,
            "usage_contexts": 3,
            "entities": 5,
            "unknown_terms": 3,
        }.items():
            item = normalized.get(key)
            if isinstance(item, list):
                normalized[key] = item[:limit]
        for key, limit in {
            "key_concepts": 60,
            "usage_contexts": 40,
            "entities": 80,
            "unknown_terms": 80,
        }.items():
            item = normalized.get(key)
            if isinstance(item, list):
                normalized[key] = [
                    value[:limit] if isinstance(value, str) else value
                    for value in item
                ]
        return normalized


class ClassificationProfileBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profiles: list[ClassificationProfile] = Field(min_length=1, max_length=12)


def build_profile_prompt(rows: list[list[Any]]) -> str:
    return f"""你是事实型 Classification Profile 压缩器，不是分类器。
为每条输入生成一个长期可复用的紧凑机器表示，只压缩已有证据，不补充外部知识。

硬约束：
1. 每个 content_id 必须且只能输出一次，并原样保留 source_evidence_level。
2. A/B 输入为 [ID,证据等级,标题,一句话结论,最多3条核心观点,最多5个已有实体]。
3. C 输入为 [ID,C,标题,最多300字符的已有简介]；不得假设它拥有摘要。
4. main_subject 只写主要讨论对象；content_goal 只写内容希望帮助观看者完成什么。
5. key_concepts 最多5个，usage_contexts 最多3个，entities 最多5个，unknown_terms 最多3个。
6. 所有字段使用短语或一句短句，不写解释段落；中文输出，专有名词保留英文。
7. 不得生成、建议或命名 Domain、Subdomain、Content Type、Taxonomy 节点或人工分类。
8. 不得写“应归入”“建议分类为”等分类指令，不得输出 domain、category、label 等额外字段。
9. unknown_terms 只记录输入中确实存在且无法判断含义的专有词；没有则为空。
10. main_subject 和 content_goal 必须是非空字符串；无法从证据判断 content_goal 时写“信息不足”，不得留空或猜测。
11. 证据不足时只允许数组字段留空。只输出 JSON。

精简输出结构：{PROFILE_SCHEMA_HINT}
输入行：
{_rows_text(rows)}"""


def validate_profile_batch(
    value: ClassificationProfileBatch,
    expected_levels: dict[str, EvidenceLevel],
) -> None:
    actual = [item.content_id for item in value.profiles]
    if len(actual) != len(set(actual)) or set(actual) != set(expected_levels):
        raise PipelineError(
            "Classification Profile 未逐一覆盖本批短 ID",
            code="profile_content_id_mismatch",
            retryable=False,
        )
    wrong_levels = [
        item.content_id
        for item in value.profiles
        if item.source_evidence_level != expected_levels[item.content_id]
    ]
    if wrong_levels:
        raise PipelineError(
            "Classification Profile 改变了 source_evidence_level",
            code="profile_evidence_level_mismatch",
            retryable=False,
        )
    polluted = [item.content_id for item in value.profiles if profile_is_polluted(item)]
    if polluted:
        raise PipelineError(
            "Classification Profile 包含显式分类指令或 Taxonomy 标记",
            code="profile_domain_pollution",
            retryable=False,
        )


def profile_is_polluted(profile: ClassificationProfile) -> bool:
    text = "\n".join(
        [
            profile.main_subject,
            profile.content_goal,
            *profile.key_concepts,
            *profile.usage_contexts,
            *profile.entities,
            *profile.unknown_terms,
        ]
    )
    patterns = (
        r"(?:建议|应当|应该)?\s*(?:归入|归类到|分类为|标记为)",
        r"\b(?:domain|subdomain|content[ _-]?type|taxonomy)[：:]",
        r"(?:一级|二级)\s*(?:领域|分类)[：:]",
    )
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def select_profile_rows(
    cards: list[dict[str, Any]], *, limit: int, seed: int
) -> tuple[list[list[Any]], dict[str, str]]:
    compact = build_compact_corpus(cards)
    eligible = [row for row in compact["rows"] if row[1] in {"A", "B", "C"}]
    random.Random(seed).shuffle(eligible)
    selected = eligible[:limit]
    if len(selected) < limit:
        raise ValueError("A/B/C 卡片不足，无法生成指定数量的 Classification Profile")
    return selected, compact["id_map"]


def profile_row(profile: ClassificationProfile) -> list[Any]:
    return [
        profile.content_id,
        profile.source_evidence_level,
        profile.main_subject,
        profile.content_goal,
        profile.key_concepts,
        profile.usage_contexts,
        profile.entities,
        profile.unknown_terms,
    ]


def compression_metrics(
    compact_rows: list[list[Any]], profiles: list[ClassificationProfile]
) -> dict[str, int | float | bool]:
    by_id = {profile.content_id: profile for profile in profiles}
    ordered_profiles = [by_id[str(row[0])] for row in compact_rows]
    profile_rows = [profile_row(item) for item in ordered_profiles]
    compact_text = _rows_text(compact_rows)
    profile_text = _rows_text(profile_rows)
    compact_estimate = estimate_tokens(compact_text)
    profile_estimate = estimate_tokens(profile_text)
    character_reduction = 1 - len(profile_text) / max(len(compact_text), 1)
    token_reduction = 1 - profile_estimate / max(compact_estimate, 1)
    return {
        "compact_characters": len(compact_text),
        "profile_characters": len(profile_text),
        "character_reduction": round(character_reduction, 4),
        "compact_estimated_tokens": compact_estimate,
        "profile_estimated_tokens": profile_estimate,
        "estimated_token_reduction": round(token_reduction, 4),
        "average_profile_characters": round(len(profile_text) / max(len(profiles), 1), 2),
        "compression_gate_passed": token_reduction >= 0.25,
    }


def estimate_tokens(text: str) -> int:
    total = 0.0
    ascii_run = 0
    for character in text:
        code = ord(character)
        if character.isascii() and character.isalnum():
            ascii_run += 1
            continue
        if ascii_run:
            total += math.ceil(ascii_run / 4)
            ascii_run = 0
        if character.isspace():
            continue
        if 0x3400 <= code <= 0x9FFF:
            total += 1
        elif character.isascii():
            total += 0.35
        else:
            total += 0.8
    if ascii_run:
        total += math.ceil(ascii_run / 4)
    return math.ceil(total)


class ClassificationProfileService:
    """Private, resumable Checkpoint 3.7A spike over one frozen Snapshot."""

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
        limit: int = 48,
        seed: int = 73,
        batch_size: int = 12,
    ) -> dict[str, Any]:
        if not 1 <= limit <= 48:
            raise ValueError("Profile Spike limit must be between 1 and 48")
        if not 1 <= batch_size <= 12:
            raise ValueError("Profile Spike batch_size must be between 1 and 12")
        snapshot = self.repository.get_snapshot(snapshot_id)
        if snapshot is None:
            raise LookupError("快照不存在")
        rows, id_map = select_profile_rows(snapshot["cards"], limit=limit, seed=seed)
        run_id = (
            f"profile-spike-s{snapshot_id}-"
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
        )
        run_dir = self.output_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        manifest = {
            "run_id": run_id,
            "kind": "classification_profile_spike",
            "production_stage": False,
            "profile_version": PROFILE_VERSION,
            "prompt_version": PROFILE_PROMPT_VERSION,
            "snapshot_id": snapshot_id,
            "snapshot_hash": snapshot["snapshot_hash"],
            "seed": seed,
            "limit": limit,
            "batch_size": batch_size,
            "selected_ids": [row[0] for row in rows],
            "selected_content_keys_hash": stable_hash(
                [id_map[str(row[0])] for row in rows]
            ),
            "status": "pending",
            "calls": [],
            "created_at": _utc_now(),
        }
        _write_json(run_dir / "manifest.json", manifest)
        return self._execute(run_dir, manifest, snapshot["cards"], resume=False)

    def materialize_snapshot(
        self,
        snapshot_id: int,
        *,
        reuse_run_id: str,
        seed: int = 73,
        batch_size: int = 12,
    ) -> dict[str, Any]:
        snapshot = self.repository.get_snapshot(snapshot_id)
        if snapshot is None:
            raise LookupError("快照不存在")
        compact = build_compact_corpus(snapshot["cards"])
        eligible_count = sum(row[1] in {"A", "B", "C"} for row in compact["rows"])
        rows, id_map = select_profile_rows(
            snapshot["cards"], limit=eligible_count, seed=seed
        )
        source_dir = self.output_dir / reuse_run_id
        source_manifest_path = source_dir / "manifest.json"
        source_profiles_path = source_dir / "profiles.jsonl"
        if not source_manifest_path.is_file() or not source_profiles_path.is_file():
            raise LookupError("复用的 Classification Profile Run 不存在")
        source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
        if (
            source_manifest.get("status") != "completed"
            or source_manifest.get("snapshot_hash") != snapshot["snapshot_hash"]
            or source_manifest.get("prompt_version") != PROFILE_PROMPT_VERSION
            or not source_manifest.get("gates")
            or not all(source_manifest["gates"].values())
        ):
            raise PipelineError(
                "复用的 Classification Profile Run 未通过 3.7A",
                code="profile_reuse_unaccepted",
                retryable=False,
            )
        reused: list[dict[str, Any]] = []
        for line in source_profiles_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            value = json.loads(line)
            reused.append(
                {
                    key: value[key]
                    for key in ClassificationProfile.model_fields
                    if key in value
                }
            )
        reused_ids = {str(value["content_id"]) for value in reused}
        selected_ids = [str(row[0]) for row in rows]
        if not reused_ids <= set(selected_ids):
            raise PipelineError(
                "复用 Profile 不属于当前 Snapshot",
                code="profile_reuse_id_mismatch",
                retryable=False,
            )
        run_id = (
            f"profile-corpus-s{snapshot_id}-"
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
        )
        run_dir = self.output_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        _write_jsonl(run_dir / "reused-profiles.jsonl", reused)
        generation_ids = [short_id for short_id in selected_ids if short_id not in reused_ids]
        manifest = {
            "run_id": run_id,
            "kind": "classification_profile_corpus",
            "production_stage": False,
            "profile_version": PROFILE_VERSION,
            "prompt_version": PROFILE_PROMPT_VERSION,
            "snapshot_id": snapshot_id,
            "snapshot_hash": snapshot["snapshot_hash"],
            "seed": seed,
            "limit": eligible_count,
            "batch_size": batch_size,
            "selected_ids": selected_ids,
            "generation_ids": generation_ids,
            "reused_count": len(reused),
            "reuse_run_id": reuse_run_id,
            "reuse_profiles_hash": source_manifest.get("profiles_hash"),
            "selected_content_keys_hash": stable_hash(
                [id_map[str(row[0])] for row in rows]
            ),
            "status": "pending",
            "calls": [],
            "created_at": _utc_now(),
        }
        _write_json(run_dir / "manifest.json", manifest)
        return self._execute(run_dir, manifest, snapshot["cards"], resume=False)

    def resume_spike(self, run_id: str) -> dict[str, Any]:
        run_dir = self.output_dir / run_id
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.is_file():
            raise LookupError("Profile Spike 不存在")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("kind") not in {
            "classification_profile_spike",
            "classification_profile_corpus",
        }:
            raise PipelineError(
                "运行目录不是 Classification Profile Spike",
                code="profile_resume_corrupt",
                retryable=False,
            )
        snapshot = self.repository.get_snapshot(int(manifest["snapshot_id"]))
        if snapshot is None or snapshot["snapshot_hash"] != manifest["snapshot_hash"]:
            raise PipelineError(
                "Profile Spike 的冻结 Snapshot 不存在或 Hash 改变",
                code="profile_snapshot_mismatch",
                retryable=False,
            )
        return self._execute(run_dir, manifest, snapshot["cards"], resume=True)

    def _execute(
        self,
        run_dir: Path,
        manifest: dict[str, Any],
        cards: list[dict[str, Any]],
        *,
        resume: bool,
    ) -> dict[str, Any]:
        rows, id_map = select_profile_rows(
            cards, limit=int(manifest["limit"]), seed=int(manifest["seed"])
        )
        if [row[0] for row in rows] != manifest["selected_ids"]:
            raise PipelineError(
                "Profile Spike 恢复时输入顺序改变",
                code="profile_resume_input_mismatch",
                retryable=False,
            )
        generation_ids = set(manifest.get("generation_ids") or manifest["selected_ids"])
        generation_rows = [row for row in rows if str(row[0]) in generation_ids]
        batches = [
            generation_rows[index:index + int(manifest["batch_size"])]
            for index in range(0, len(generation_rows), int(manifest["batch_size"]))
        ]
        provider = self.provider_factory("taxonomy_profile")
        repair_provider = self.provider_factory("taxonomy_repair")
        caller = AuditedJsonCaller(
            provider=provider, repair_provider=repair_provider
        )
        reused_path = run_dir / "reused-profiles.jsonl"
        all_profiles: list[ClassificationProfile] = (
            [
                ClassificationProfile.model_validate(json.loads(line))
                for line in reused_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            if reused_path.is_file()
            else []
        )
        calls: list[dict[str, Any]] = []
        manifest.update(status="running", model=provider.model, calls=[])
        _write_json(run_dir / "manifest.json", manifest)
        try:
            for index, batch in enumerate(batches, start=1):
                prompt = build_profile_prompt(batch)
                call_dir = run_dir / f"batch-{index:03d}"
                expected_levels = {
                    str(row[0]): str(row[1]) for row in batch
                }
                result, audit = caller.call(
                    call_dir=call_dir,
                    prompt=prompt,
                    prompt_version=PROFILE_PROMPT_VERSION,
                    schema=ClassificationProfileBatch,
                    schema_hint=PROFILE_SCHEMA_HINT,
                    max_tokens=4096,
                    input_ids=[str(row[0]) for row in batch],
                    validator=lambda value, expected=expected_levels: (
                        validate_profile_batch(value, expected)  # type: ignore[arg-type]
                    ),
                    resume=resume and call_dir.exists(),
                )
                all_profiles.extend(result.profiles)
                calls.append(_call_summary(index, audit, call_dir))
                manifest["calls"] = calls
                _write_json(run_dir / "manifest.json", manifest)
        except Exception as exc:
            manifest.update(
                status="failed",
                error_code=getattr(exc, "code", type(exc).__name__),
                error_message=str(exc),
                calls=calls,
                updated_at=_utc_now(),
            )
            _write_json(run_dir / "manifest.json", manifest)
            raise

        profiles_by_id = {item.content_id: item for item in all_profiles}
        ordered = [profiles_by_id[str(row[0])] for row in rows]
        metrics = compression_metrics(rows, ordered)
        repair_count = sum(bool(call["repair_required"]) for call in calls)
        missing_field_count = sum(int(call["missing_field_count"]) for call in calls)
        raw_pollution_error_count = sum(
            int(call["raw_pollution_error_count"]) for call in calls
        )
        pollution_count = sum(profile_is_polluted(item) for item in ordered)
        schema_success = len(ordered) == len(rows)
        gates = {
            "schema_success_100_percent": schema_success,
            "domain_pollution_zero": (
                pollution_count == 0 and raw_pollution_error_count == 0
            ),
            "repair_zero": repair_count == 0,
            "estimated_token_reduction_at_least_25_percent": bool(
                metrics["compression_gate_passed"]
            ),
        }
        _write_jsonl(
            run_dir / "profiles.jsonl",
            [
                {
                    **item.model_dump(mode="json"),
                    "content_key": id_map[item.content_id],
                    "profile_version": PROFILE_VERSION,
                }
                for item in ordered
            ],
        )
        _write_jsonl(
            run_dir / "profile-discovery-view.jsonl",
            [profile_row(item) for item in ordered],
        )
        manifest.update(
            status="completed" if all(gates.values()) else "gate_failed",
            completed_count=len(ordered),
            evidence_counts={
                level: sum(item.source_evidence_level == level for item in ordered)
                for level in ("A", "B", "C")
            },
            generated_count=len(generation_ids),
            reused_count=len(ordered) - len(generation_ids),
            calls=calls,
            usage=_aggregate_calls(calls),
            compression=metrics,
            raw_schema_success_rate=round(
                sum(not bool(call["repair_required"]) for call in calls)
                / max(len(calls), 1),
                4,
            ),
            repair_count=repair_count,
            missing_field_count=missing_field_count,
            pollution_count=pollution_count,
            raw_pollution_error_count=raw_pollution_error_count,
            gates=gates,
            profiles_hash=stable_hash(
                [item.model_dump(mode="json") for item in ordered]
            ),
            finished_at=_utc_now(),
        )
        _write_json(run_dir / "manifest.json", manifest)
        return {**manifest, "run_dir": str(run_dir)}


def _call_summary(
    index: int, audit: dict[str, Any], call_dir: Path
) -> dict[str, Any]:
    usage, elapsed = _combined_usage(audit)
    validation_path = call_dir / "validation-error.txt"
    validation_error = (
        validation_path.read_text(encoding="utf-8") if validation_path.is_file() else ""
    )
    return {
        "batch": index,
        "status": audit.get("status"),
        "input_count": audit.get("input_count"),
        "input_chars": audit.get("input_chars"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "cached_tokens": _nested_usage(usage, "prompt_tokens_details", "cached_tokens"),
        "reasoning_tokens": _nested_usage(
            usage, "completion_tokens_details", "reasoning_tokens"
        ),
        "elapsed_seconds": elapsed,
        "repair_required": bool(audit.get("repair")),
        "request_attempt_count": audit.get("request_attempt_count"),
        "missing_field_count": validation_error.count("Field required"),
        "raw_pollution_error_count": validation_error.count(
            "profile_domain_pollution"
        ),
    }


def _combined_usage(audit: dict[str, Any]) -> tuple[dict[str, Any], float]:
    repair = audit.get("repair") or {}
    sources = [audit, *(audit.get("attempt_history") or [])]
    if repair:
        sources.extend([repair, *(repair.get("attempt_history") or [])])
    usage_values = [source.get("usage") or {} for source in sources]
    numeric_keys = {
        key
        for usage in usage_values
        for key, value in usage.items()
        if isinstance(value, (int, float))
    }
    combined: dict[str, Any] = {
        key: sum(
            value
            for usage in usage_values
            if isinstance((value := usage.get(key)), (int, float))
        )
        for key in numeric_keys
    }
    for group, key in (
        ("prompt_tokens_details", "cached_tokens"),
        ("completion_tokens_details", "reasoning_tokens"),
    ):
        values = [
            details.get(key)
            for usage in usage_values
            if isinstance((details := usage.get(group)), dict)
        ]
        if any(isinstance(value, (int, float)) for value in values):
            combined[group] = {
                key: sum(value for value in values if isinstance(value, (int, float)))
            }
    elapsed = sum(float(source.get("elapsed_seconds") or 0) for source in sources)
    return combined, round(elapsed, 3)


def _aggregate_calls(calls: list[dict[str, Any]]) -> dict[str, int | float]:
    return {
        "prompt_tokens": sum(int(call.get("prompt_tokens") or 0) for call in calls),
        "completion_tokens": sum(
            int(call.get("completion_tokens") or 0) for call in calls
        ),
        "total_tokens": sum(int(call.get("total_tokens") or 0) for call in calls),
        "cached_tokens": sum(int(call.get("cached_tokens") or 0) for call in calls),
        "reasoning_tokens": sum(
            int(call.get("reasoning_tokens") or 0) for call in calls
        ),
        "elapsed_seconds": round(
            sum(float(call.get("elapsed_seconds") or 0) for call in calls), 3
        ),
    }


def _nested_usage(usage: dict[str, Any], group: str, key: str) -> int | None:
    value = usage.get(group)
    if isinstance(value, dict) and isinstance(value.get(key), (int, float)):
        return int(value[key])
    return None


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _rows_text(rows: list[list[Any]]) -> str:
    return "\n".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in rows
    )


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _write_jsonl(path: Path, values: list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
            for value in values
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
