from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from shiliu.domain import PipelineError
from shiliu.llm import OpenAICompatibleProvider
from shiliu.taxonomy.candidates import TopLevelDomainDraft
from shiliu.taxonomy.discovery import build_compact_corpus
from shiliu.taxonomy.model_calls import AuditedJsonCaller
from shiliu.taxonomy.run_repository import TaxonomyRunRepository
from shiliu.taxonomy.workflow import TaxonomyWorkflow


COMPARISON_VERSION = "classification-profile-paired-comparison-v1"
ANALYSIS_VERSION = "classification-profile-paired-analysis-v2"
ALIGNMENT_PROMPT_VERSION = "domain-semantic-alignment-v1"
ALIGNMENT_SCHEMA_HINT = (
    '{"matches":[{"source_id":"d_01","target_ids":["d_02"],'
    '"relation":"equivalent|broader_narrower|related|missing",'
    '"reason":"短理由"}],"summary":"短总结"}'
)


class DomainMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    target_ids: list[str] = Field(default_factory=list, max_length=2)
    relation: Literal["equivalent", "broader_narrower", "related", "missing"]
    reason: str = Field(min_length=1, max_length=200)


class DomainAlignmentReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matches: list[DomainMatch] = Field(min_length=1, max_length=12)
    summary: str = Field(min_length=1, max_length=400)


def build_alignment_prompt(
    source: TopLevelDomainDraft,
    target: TopLevelDomainDraft,
    *,
    source_label: str,
    target_label: str,
) -> str:
    return f"""你是独立的一级 Domain 语义对齐评审器，只比较结构，不修改任何 Draft。
逐一判断 {source_label} 的每个节点是否在 {target_label} 中被保留。
综合名称语义、定义、includes/excludes、supporting IDs 重叠和 representative IDs。
equivalent 表示语义边界基本等价；broader_narrower 表示因合并或拆分而粒度不同但核心领域仍被保留；
related 表示仅相关、不能视为恢复；missing 表示没有对应领域。
每个 source_id 必须且只能输出一次；target_ids 只能来自目标 Draft，最多 2 个；missing 时必须为空。
不得读取或猜测卡片内容，不得建议分类，不得生成新 Domain。只输出 JSON。

精简输出结构：{ALIGNMENT_SCHEMA_HINT}
Source {source_label}：{_compact_json(_draft_payload(source))}
Target {target_label}：{_compact_json(_draft_payload(target))}"""


def validate_alignment(
    value: DomainAlignmentReport,
    *,
    source_ids: set[str],
    target_ids: set[str],
) -> None:
    actual = [item.source_id for item in value.matches]
    if len(actual) != len(set(actual)) or set(actual) != source_ids:
        raise PipelineError(
            "Domain Alignment 未逐一覆盖 Source 节点",
            code="comparison_alignment_source_mismatch",
            retryable=False,
        )
    for item in value.matches:
        if not set(item.target_ids) <= target_ids:
            raise PipelineError(
                "Domain Alignment 引用了未知 Target 节点",
                code="comparison_alignment_target_mismatch",
                retryable=False,
            )
        if (item.relation == "missing") != (not item.target_ids):
            raise PipelineError(
                "Domain Alignment relation 与 target_ids 不一致",
                code="comparison_alignment_relation_mismatch",
                retryable=False,
            )


class ProfileDiscoveryComparisonService:
    """Private, resumable Checkpoint 3.7B paired experiment."""

    def __init__(
        self,
        *,
        workflow: TaxonomyWorkflow,
        run_repository: TaxonomyRunRepository,
        provider_factory,
        output_dir: Path,
        profile_output_dir: Path,
    ) -> None:
        self.workflow = workflow
        self.run_repository = run_repository
        self.provider_factory = provider_factory
        self.output_dir = output_dir
        self.profile_output_dir = profile_output_dir

    def run(
        self,
        *,
        snapshot_id: int,
        profile_run_id: str,
        pair_seeds: tuple[int, int] = (73, 137),
        batch_size: int = 24,
    ) -> dict[str, Any]:
        profile_manifest = self._accepted_profile_manifest(profile_run_id)
        if int(profile_manifest.get("snapshot_id") or 0) != snapshot_id:
            raise ValueError("Profile Run and Comparison Snapshot must match")
        if len(set(pair_seeds)) != 2:
            raise ValueError("Checkpoint 3.7B requires two distinct pair seeds")
        selected_ids = [str(value) for value in profile_manifest["selected_ids"]]
        if len(selected_ids) != 48 or len(set(selected_ids)) != 48:
            raise ValueError("Checkpoint 3.7B requires exactly 48 unique Profile IDs")
        comparison_id = (
            "profile-comparison-"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        )
        comparison_dir = self.output_dir / comparison_id
        comparison_dir.mkdir(parents=True, exist_ok=False)
        runs: dict[str, int] = {}
        for pair_index, seed in enumerate(pair_seeds, start=1):
            for representation, suffix in (
                ("compact", "A"),
                ("classification_profile_v1", "B"),
            ):
                label = f"{suffix}{pair_index}"
                runs[label] = self.workflow.create_run(
                    snapshot_id=snapshot_id,
                    run_kind=f"profile_comparison_{label.lower()}",
                    seed=seed,
                    batch_size=batch_size,
                    limit=None,
                    include_assignment=False,
                    representation=representation,
                    profile_run_id=(
                        profile_run_id
                        if representation == "classification_profile_v1"
                        else None
                    ),
                    selected_ids=selected_ids,
                )
        manifest = {
            "comparison_id": comparison_id,
            "kind": "classification_profile_paired_comparison",
            "version": COMPARISON_VERSION,
            "production_stage": False,
            "snapshot_id": snapshot_id,
            "snapshot_hash": profile_manifest["snapshot_hash"],
            "profile_run_id": profile_run_id,
            "profile_hash": profile_manifest["profiles_hash"],
            "selected_ids_hash": _stable_hash(selected_ids),
            "pair_seeds": list(pair_seeds),
            "batch_size": batch_size,
            "run_ids": runs,
            "status": "pending",
            "created_at": _utc_now(),
        }
        _write_json(comparison_dir / "manifest.json", manifest)
        return self._execute(comparison_dir, manifest, profile_manifest)

    def resume(self, comparison_id: str) -> dict[str, Any]:
        comparison_dir = self.output_dir / comparison_id
        manifest_path = comparison_dir / "manifest.json"
        if not manifest_path.is_file():
            raise LookupError("Profile Discovery Comparison 不存在")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        profile_manifest = self._accepted_profile_manifest(
            str(manifest["profile_run_id"])
        )
        if (
            manifest.get("version") != COMPARISON_VERSION
            or manifest.get("profile_hash") != profile_manifest.get("profiles_hash")
        ):
            raise PipelineError(
                "Profile Discovery Comparison 输入已改变",
                code="comparison_resume_mismatch",
                retryable=False,
            )
        if (
            manifest.get("status") in {"completed", "gate_failed"}
            and manifest.get("analysis_version") == ANALYSIS_VERSION
        ):
            return {**manifest, "comparison_dir": str(comparison_dir)}
        return self._execute(comparison_dir, manifest, profile_manifest)

    def _execute(
        self,
        comparison_dir: Path,
        manifest: dict[str, Any],
        profile_manifest: dict[str, Any],
    ) -> dict[str, Any]:
        manifest["status"] = "running"
        _write_json(comparison_dir / "manifest.json", manifest)
        for label, run_id in manifest["run_ids"].items():
            run = self.run_repository.get_run(int(run_id))
            if run is None:
                raise PipelineError(
                    f"Comparison Run {label} 不存在",
                    code="comparison_run_missing",
                    retryable=False,
                )
            if run["status"] not in {"completed", "quality_failed"}:
                self.workflow.execute(int(run_id), resume=True)

        run_metrics = {
            label: self._run_metrics(int(run_id), manifest)
            for label, run_id in manifest["run_ids"].items()
        }
        self._validate_pair_plans(manifest)
        alignments = {
            "pair1": self._align(
                comparison_dir, "pair1", run_metrics["A1"], run_metrics["B1"]
            ),
            "pair2": self._align(
                comparison_dir, "pair2", run_metrics["A2"], run_metrics["B2"]
            ),
            "compact_stability": self._align(
                comparison_dir,
                "compact-stability",
                run_metrics["A1"],
                run_metrics["A2"],
            ),
            "profile_stability": self._align(
                comparison_dir,
                "profile-stability",
                run_metrics["B1"],
                run_metrics["B2"],
            ),
        }
        pair_metrics = {
            pair: self._pair_metrics(
                run_metrics[f"A{index}"],
                run_metrics[f"B{index}"],
                alignments[pair],
            )
            for index, pair in ((1, "pair1"), (2, "pair2"))
        }
        direct_compact = sum(
            run_metrics[label]["direct_input_prompt_tokens"] for label in ("A1", "A2")
        ) / 2
        direct_profile = sum(
            run_metrics[label]["direct_input_prompt_tokens"] for label in ("B1", "B2")
        ) / 2
        saved_per_use = direct_compact - direct_profile
        generation_tokens = int((profile_manifest.get("usage") or {}).get("total_tokens") or 0)
        economics = {
            "one_time_profile_generation_tokens": generation_tokens,
            "average_compact_direct_prompt_tokens": round(direct_compact, 2),
            "average_profile_direct_prompt_tokens": round(direct_profile, 2),
            "direct_prompt_tokens_saved_per_use": round(saved_per_use, 2),
            "break_even_uses": (
                math.ceil(generation_tokens / saved_per_use) if saved_per_use > 0 else None
            ),
        }
        alignment_repairs = sum(
            int(value["repair_required"]) for value in alignments.values()
        )
        all_runs = list(run_metrics.values())
        gates = {
            "profile_reduction_at_least_25_percent": (
                float((profile_manifest.get("compression") or {}).get(
                    "estimated_token_reduction", 0
                ))
                >= 0.25
            ),
            "weighted_domain_recovery_at_least_85_percent": all(
                value["weighted_domain_recovery"] >= 0.85
                for value in pair_metrics.values()
            ),
            "c_domain_signal_drop_at_most_5_points": all(
                value["c_domain_signal_delta"] >= -0.05
                for value in pair_metrics.values()
            ),
            "c_content_type_ambiguity_increase_at_most_5_points": all(
                value["c_content_type_ambiguity_delta"] <= 0.05
                for value in pair_metrics.values()
            ),
            "ambiguity_increase_at_most_5_points": all(
                value["ambiguity_rate_delta"] <= 0.05
                for value in pair_metrics.values()
            ),
            "entity_and_content_type_leakage_zero": all(
                value["entity_leakage"] == 0
                and value["content_type_leakage"] == 0
                for value in all_runs
            ),
            "repair_zero": (
                alignment_repairs == 0
                and all(value["repair_count"] == 0 for value in all_runs)
            ),
            "quality_gate_passed": all(value["quality_passed"] for value in all_runs),
        }
        sanitized_run_metrics = {
            label: {key: value for key, value in metrics.items() if key != "draft"}
            for label, metrics in run_metrics.items()
        }
        result = {
            **manifest,
            "analysis_version": ANALYSIS_VERSION,
            "status": "completed" if all(gates.values()) else "gate_failed",
            "run_metrics": sanitized_run_metrics,
            "pair_metrics": pair_metrics,
            "stability": {
                "compact_weighted_recovery": alignments["compact_stability"][
                    "weighted_recovery"
                ],
                "profile_weighted_recovery": alignments["profile_stability"][
                    "weighted_recovery"
                ],
            },
            "alignment_usage": _aggregate_alignment_usage(alignments),
            "economics": economics,
            "gates": gates,
            "finished_at": _utc_now(),
        }
        _write_json(comparison_dir / "result.json", result)
        _write_json(comparison_dir / "manifest.json", result)
        return {**result, "comparison_dir": str(comparison_dir)}

    def _accepted_profile_manifest(self, profile_run_id: str) -> dict[str, Any]:
        path = self.profile_output_dir / profile_run_id / "manifest.json"
        if not path.is_file():
            raise LookupError("Classification Profile Run 不存在")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if (
            manifest.get("status") != "completed"
            or manifest.get("profile_version") != "classification_profile_v1"
            or manifest.get("prompt_version") != "classification-profile-generation-v2"
            or not manifest.get("gates")
            or not all(manifest["gates"].values())
        ):
            raise PipelineError(
                "Classification Profile Run 未通过 3.7A",
                code="comparison_profile_unaccepted",
                retryable=False,
            )
        return manifest

    def _run_metrics(
        self, run_id: int, comparison_manifest: dict[str, Any]
    ) -> dict[str, Any]:
        run = self.run_repository.get_run(run_id)
        assert run is not None
        run_dir = self.workflow.output_dir / f"run-{run_id:06d}"
        draft = TopLevelDomainDraft.model_validate_json(
            (run_dir / "taxonomy-draft.json").read_text(encoding="utf-8")
        )
        local = json.loads((run_dir / "local-candidates.json").read_text(encoding="utf-8"))
        content_types = json.loads((run_dir / "content-types.json").read_text(encoding="utf-8"))
        quality = json.loads(
            (run_dir / "quality-gate" / "quality-result.json").read_text(encoding="utf-8")
        )
        stages = self.run_repository.list_stages(run_id)
        snapshot = self.workflow.snapshot_repository.get_snapshot(
            int(comparison_manifest["snapshot_id"])
        )
        assert snapshot is not None
        compact = build_compact_corpus(snapshot["cards"])
        evidence = {str(row[0]): str(row[1]) for row in compact["rows"]}
        selected = set(self._batch_ids(run_dir))
        c_ids = {short_id for short_id in selected if evidence.get(short_id) == "C"}
        support_ids = {
            value for node in draft.domains for value in node.supporting_ids
        }
        domain_signal_ids = {
            value
            for batch in local
            for group in (batch.get("domains", []), batch.get("topic_hints", []))
            for node in group
            for value in node.get("supporting_ids", [])
        }
        local_ambiguous = {
            value for batch in local for value in batch.get("ambiguous_ids", [])
        }
        content_support_ids = {
            value
            for node in content_types.get("content_types", [])
            for value in node.get("supporting_ids", [])
        }
        content_ambiguous = set(content_types.get("ambiguous_ids", []))
        issue_codes = {
            issue.get("code")
            for group in ("blocking_issues", "warnings")
            for issue in quality.get(group, [])
        }
        repair_count = 0
        request_retry_count = 0
        for audit_path in run_dir.glob("**/audit.json"):
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            repair_count += int(bool(audit.get("repair")))
            request_retry_count += max(int(audit.get("request_attempt_count") or 1) - 1, 0)
        direct_stages = {"local_discovery", "content_type_discovery"}
        return {
            "run_id": run_id,
            "status": run["status"],
            "representation": run["parameters"].get("representation", "compact"),
            "draft": draft.model_dump(mode="json"),
            "domain_count": len(draft.domains),
            "support_coverage": round(len(support_ids) / max(len(selected), 1), 4),
            "c_representative_support_rate": round(
                len(support_ids & c_ids) / max(len(c_ids), 1), 4
            ),
            "c_domain_signal_rate": round(
                len(domain_signal_ids & c_ids) / max(len(c_ids), 1), 4
            ),
            "c_local_ambiguity_rate": round(
                len(local_ambiguous & c_ids) / max(len(c_ids), 1), 4
            ),
            "c_content_type_support_rate": round(
                len(content_support_ids & c_ids) / max(len(c_ids), 1), 4
            ),
            "c_content_type_ambiguity_rate": round(
                len(content_ambiguous & c_ids) / max(len(c_ids), 1), 4
            ),
            "ambiguity_rate": round(
                len(local_ambiguous | content_ambiguous) / max(len(selected), 1), 4
            ),
            "local_ambiguous_count": len(local_ambiguous),
            "content_type_ambiguous_count": len(content_ambiguous),
            "topic_hint_count": sum(len(batch.get("topic_hints", [])) for batch in local),
            "entity_leakage": int("entity_leakage" in issue_codes),
            "content_type_leakage": int("content_type_leakage" in issue_codes),
            "invalid_supporting_ids": int("invalid_supporting_ids" in issue_codes),
            "quality_passed": bool(quality.get("passed")),
            "repair_count": repair_count,
            "request_retry_count": request_retry_count,
            "prompt_tokens": sum(int(stage.get("input_tokens") or 0) for stage in stages),
            "completion_tokens": sum(int(stage.get("output_tokens") or 0) for stage in stages),
            "reasoning_tokens": sum(int(stage.get("reasoning_tokens") or 0) for stage in stages),
            "elapsed_seconds": round(
                sum(float(stage.get("elapsed_seconds") or 0) for stage in stages), 3
            ),
            "direct_input_prompt_tokens": sum(
                int(stage.get("input_tokens") or 0)
                for stage in stages
                if stage["stage_name"] in direct_stages
            ),
        }

    def _align(
        self,
        comparison_dir: Path,
        name: str,
        source_metrics: dict[str, Any],
        target_metrics: dict[str, Any],
    ) -> dict[str, Any]:
        source = TopLevelDomainDraft.model_validate(source_metrics["draft"])
        target = TopLevelDomainDraft.model_validate(target_metrics["draft"])
        prompt = build_alignment_prompt(
            source, target, source_label=f"source-{name}", target_label=f"target-{name}"
        )
        caller = AuditedJsonCaller(
            provider=self.provider_factory("taxonomy_validator"),
            repair_provider=self.provider_factory("taxonomy_repair"),
        )
        call_dir = comparison_dir / "alignments" / name
        result, audit = caller.call(
            call_dir=call_dir,
            prompt=prompt,
            prompt_version=ALIGNMENT_PROMPT_VERSION,
            schema=DomainAlignmentReport,
            schema_hint=ALIGNMENT_SCHEMA_HINT,
            max_tokens=4096,
            input_ids=[node.id for node in source.domains],
            validator=lambda value: validate_alignment(
                value,
                source_ids={node.id for node in source.domains},
                target_ids={node.id for node in target.domains},
            ),
            resume=call_dir.exists(),
        )
        weights = {node.id: len(node.supporting_ids) for node in source.domains}
        recovered = {
            item.source_id
            for item in result.matches
            if item.relation in {"equivalent", "broader_narrower"}
        }
        total_weight = sum(weights.values())
        weighted = sum(weights[item] for item in recovered) / max(total_weight, 1)
        return {
            "weighted_recovery": round(weighted, 4),
            "source_domain_count": len(source.domains),
            "target_domain_count": len(target.domains),
            "relation_counts": {
                relation: sum(item.relation == relation for item in result.matches)
                for relation in ("equivalent", "broader_narrower", "related", "missing")
            },
            "repair_required": bool(audit.get("repair")),
            "usage": _audit_usage(audit),
        }

    def _pair_metrics(
        self,
        compact: dict[str, Any],
        profile: dict[str, Any],
        alignment: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "weighted_domain_recovery": alignment["weighted_recovery"],
            "compact_domain_count": compact["domain_count"],
            "profile_domain_count": profile["domain_count"],
            "compact_c_representative_support_rate": compact[
                "c_representative_support_rate"
            ],
            "profile_c_representative_support_rate": profile[
                "c_representative_support_rate"
            ],
            "compact_c_domain_signal_rate": compact["c_domain_signal_rate"],
            "profile_c_domain_signal_rate": profile["c_domain_signal_rate"],
            "c_domain_signal_delta": round(
                profile["c_domain_signal_rate"] - compact["c_domain_signal_rate"], 4
            ),
            "compact_c_content_type_support_rate": compact[
                "c_content_type_support_rate"
            ],
            "profile_c_content_type_support_rate": profile[
                "c_content_type_support_rate"
            ],
            "compact_c_content_type_ambiguity_rate": compact[
                "c_content_type_ambiguity_rate"
            ],
            "profile_c_content_type_ambiguity_rate": profile[
                "c_content_type_ambiguity_rate"
            ],
            "c_content_type_ambiguity_delta": round(
                profile["c_content_type_ambiguity_rate"]
                - compact["c_content_type_ambiguity_rate"],
                4,
            ),
            "compact_ambiguity_rate": compact["ambiguity_rate"],
            "profile_ambiguity_rate": profile["ambiguity_rate"],
            "ambiguity_rate_delta": round(
                profile["ambiguity_rate"] - compact["ambiguity_rate"], 4
            ),
            "compact_total_tokens": compact["prompt_tokens"] + compact["completion_tokens"],
            "profile_total_tokens": profile["prompt_tokens"] + profile["completion_tokens"],
            "compact_elapsed_seconds": compact["elapsed_seconds"],
            "profile_elapsed_seconds": profile["elapsed_seconds"],
        }

    def _validate_pair_plans(self, manifest: dict[str, Any]) -> None:
        for index in (1, 2):
            compact_dir = self.workflow.output_dir / f"run-{manifest['run_ids'][f'A{index}']:06d}"
            profile_dir = self.workflow.output_dir / f"run-{manifest['run_ids'][f'B{index}']:06d}"
            compact_plan = json.loads((compact_dir / "batch-plan.json").read_text())
            profile_plan = json.loads((profile_dir / "batch-plan.json").read_text())
            if compact_plan != profile_plan:
                raise PipelineError(
                    f"Pair {index} 的输入顺序或批次不一致",
                    code="comparison_pair_plan_mismatch",
                    retryable=False,
                )

    @staticmethod
    def _batch_ids(run_dir: Path) -> list[str]:
        plan = json.loads((run_dir / "batch-plan.json").read_text(encoding="utf-8"))
        return [value for batch in plan["batches"] for value in batch]


def _draft_payload(draft: TopLevelDomainDraft) -> list[dict[str, Any]]:
    return [
        {
            "id": node.id,
            "name": node.name,
            "definition": node.definition,
            "includes": node.includes,
            "excludes": node.excludes,
            "supporting_ids": node.supporting_ids,
            "representative_ids": node.representative_ids,
        }
        for node in draft.domains
    ]


def _audit_usage(audit: dict[str, Any]) -> dict[str, int | float]:
    sources = [audit, *(audit.get("attempt_history") or [])]
    repair = audit.get("repair") or {}
    if repair:
        sources.extend([repair, *(repair.get("attempt_history") or [])])
    usages = [value.get("usage") or {} for value in sources]
    return {
        "prompt_tokens": sum(int(value.get("prompt_tokens") or 0) for value in usages),
        "completion_tokens": sum(int(value.get("completion_tokens") or 0) for value in usages),
        "total_tokens": sum(int(value.get("total_tokens") or 0) for value in usages),
        "elapsed_seconds": round(
            sum(float(value.get("elapsed_seconds") or 0) for value in sources), 3
        ),
    }


def _aggregate_alignment_usage(values: dict[str, dict[str, Any]]) -> dict[str, int | float]:
    return {
        key: round(sum(float(value["usage"][key]) for value in values.values()), 3)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens", "elapsed_seconds")
    }


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _stable_hash(value: Any) -> str:
    import hashlib

    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
