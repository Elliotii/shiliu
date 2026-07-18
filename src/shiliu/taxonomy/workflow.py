from __future__ import annotations

import hashlib
import json
import random
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

from pydantic import BaseModel

from shiliu.domain import PipelineError
from shiliu.llm import OpenAICompatibleProvider
from shiliu.taxonomy.discovery import (
    build_compact_corpus,
)
from shiliu.taxonomy.candidates import (
    CANDIDATE_NORMALIZATION_VERSION,
    CONTENT_TYPE_CONSOLIDATION_PROMPT_VERSION,
    CONTENT_TYPE_CONSOLIDATION_SCHEMA_HINT,
    CONTENT_TYPE_DRAFT_SCHEMA_VERSION,
    CONTENT_TYPE_NORMALIZATION_VERSION,
    CONTENT_TYPE_PROMPT_VERSION,
    CONTENT_TYPE_SCHEMA_VERSION,
    CONTENT_TYPE_SCHEMA_HINT,
    LOCAL_TOP_LEVEL_PROMPT_VERSION,
    LOCAL_TOP_LEVEL_SCHEMA_VERSION,
    LOCAL_TOP_LEVEL_SCHEMA_HINT,
    TOP_LEVEL_CONSOLIDATION_PROMPT_VERSION,
    TOP_LEVEL_CONSOLIDATION_SCHEMA_HINT,
    TOP_LEVEL_DOMAIN_SCHEMA_VERSION,
    CompactCandidateTable,
    CompactContentTypeTable,
    ContentTypeDraftV1,
    ContentTypeDiscoveryOutputV1,
    DualViewDiscoveryOutputV1,
    LocalTopLevelDiscoveryOutput,
    TopLevelDomainDraft,
    build_content_type_consolidation_prompt,
    build_content_type_prompt,
    build_top_level_consolidation_prompt,
    build_top_level_local_prompt,
    normalize_candidates,
    normalize_content_types,
    validate_content_type_draft,
    validate_content_types,
    validate_local_top_level,
    validate_top_level_draft,
)
from shiliu.taxonomy.model_calls import AuditedJsonCaller
from shiliu.taxonomy.quality import (
    LOCAL_VALIDATION_PROMPT_VERSION,
    LOCAL_VALIDATION_SCHEMA_HINT,
    LocalValidationReport,
    TopLevelQualityResult,
    TopLevelRuleResult,
    TOP_LEVEL_QUALITY_GATE_VERSION,
    build_local_validation_prompt,
    combine_top_level_quality,
    evaluate_top_level_rules,
    validate_local_report,
)
from shiliu.taxonomy.repository import TaxonomyRepository
from shiliu.taxonomy.run_repository import TaxonomyRunRepository


SchemaT = TypeVar("SchemaT", bound=BaseModel)
WORKFLOW_ENGINE_VERSION = "dual-view-discovery-workflow-v9"
SUPPORTED_REPRESENTATIONS = {"compact", "classification_profile_v1"}


class TaxonomyWorkflow:
    """Minimal database-backed runner for regression and later A/B/C discovery runs."""

    def __init__(
        self,
        *,
        snapshot_repository: TaxonomyRepository,
        run_repository: TaxonomyRunRepository,
        provider_factory: Callable[[str], OpenAICompatibleProvider],
        output_dir: Path,
        profile_output_dir: Path | None = None,
    ) -> None:
        self.snapshot_repository = snapshot_repository
        self.run_repository = run_repository
        self.provider_factory = provider_factory
        self.output_dir = output_dir
        self.profile_output_dir = profile_output_dir

    def create_run(
        self,
        *,
        snapshot_id: int,
        run_kind: str = "regression",
        seed: int = 73,
        batch_size: int = 24,
        limit: int | None = 48,
        include_assignment: bool = False,
        representation: str = "compact",
        profile_run_id: str | None = None,
        selected_ids: list[str] | None = None,
        protocol_manifest: dict[str, Any] | None = None,
    ) -> int:
        if not 20 <= batch_size <= 32:
            raise ValueError("Taxonomy batch_size must be between 20 and 32")
        if include_assignment:
            raise ValueError("Checkpoint 3.5 尚未开放一级 Trial Assignment")
        if representation not in SUPPORTED_REPRESENTATIONS:
            raise ValueError("Unsupported taxonomy discovery representation")
        if representation == "classification_profile_v1" and not profile_run_id:
            raise ValueError("Profile representation requires profile_run_id")
        if representation == "compact" and profile_run_id:
            raise ValueError("Compact representation cannot use profile_run_id")
        snapshot = self.snapshot_repository.get_snapshot(snapshot_id)
        if snapshot is None:
            raise LookupError("快照不存在")
        parameters = {
            "snapshot_hash": snapshot["snapshot_hash"],
            "seed": seed,
            "batch_size": batch_size,
            "limit": limit,
            "include_assignment": include_assignment,
            "representation": representation,
            "profile_run_id": profile_run_id,
            "selected_ids": selected_ids,
            "protocol_manifest": protocol_manifest,
        }
        return self.run_repository.create_run(
            snapshot_id=snapshot_id,
            run_kind=run_kind,
            engine="batched_llm_native",
            engine_version=WORKFLOW_ENGINE_VERSION,
            parameters=parameters,
        )

    def status(self, run_id: int) -> dict[str, Any]:
        run = self.run_repository.get_run(run_id)
        if run is None:
            raise LookupError("Taxonomy Run 不存在")
        return {"run": run, "stages": self.run_repository.list_stages(run_id)}

    def create_dual_view_regression(
        self,
        *,
        snapshot_id: int,
        profile_run_id: str,
        seed: int = 73,
        batch_size: int = 24,
    ) -> int:
        snapshot = self.snapshot_repository.get_snapshot(snapshot_id)
        if snapshot is None:
            raise LookupError("快照不存在")
        manifest = self._accepted_profile_manifest(
            profile_run_id=profile_run_id,
            snapshot_hash=str(snapshot["snapshot_hash"]),
        )
        selected_ids = [str(value) for value in manifest.get("selected_ids") or []]
        if len(selected_ids) != 48 or len(set(selected_ids)) != 48:
            raise PipelineError(
                "双视图回归要求已验收的 48 条 Profile 固定输入",
                code="dual_view_profile_selection_mismatch",
                retryable=False,
            )
        return self.create_run(
            snapshot_id=snapshot_id,
            run_kind="dual_view_integration_regression",
            seed=seed,
            batch_size=batch_size,
            limit=None,
            include_assignment=False,
            representation="classification_profile_v1",
            profile_run_id=profile_run_id,
            selected_ids=selected_ids,
        )

    def create_full_discovery_run_a(
        self,
        *,
        snapshot_id: int,
        profile_run_id: str,
        seed: int = 101,
        batch_size: int = 24,
        reuse_from_run_id: int | None = None,
    ) -> int:
        snapshot = self.snapshot_repository.get_snapshot(snapshot_id)
        if snapshot is None:
            raise LookupError("快照不存在")
        expected = {
            "id": 2,
            "content_count": 131,
            "discovery_eligible_count": 128,
            "trial_assignment_only_count": 3,
            "evidence_counts": {"A": 76, "B": 17, "C": 35, "D": 3},
            "snapshot_hash": "1143f0999c569db30b2184a0129e446d3301c0c84e53a34a2807ac9f39db02a2",
        }
        for key, value in expected.items():
            if snapshot.get(key) != value:
                raise PipelineError(
                    f"Full Run A Snapshot 字段不匹配：{key}",
                    code="run_a_snapshot_contract_mismatch",
                    retryable=False,
                )
        profile_manifest = self._accepted_profile_manifest(
            profile_run_id=profile_run_id,
            snapshot_hash=str(snapshot["snapshot_hash"]),
        )
        selected_ids = [str(value) for value in profile_manifest.get("selected_ids") or []]
        if len(selected_ids) != 128 or len(set(selected_ids)) != 128:
            raise PipelineError(
                "Full Run A 要求 128 条已验收 Profile",
                code="run_a_profile_corpus_incomplete",
                retryable=False,
            )
        git_commit, git_clean = _git_state()
        if not git_clean:
            raise PipelineError(
                "冻结 Full Run A 前 Git 工作区必须干净",
                code="run_a_git_dirty",
                retryable=False,
            )
        providers = {
            role: _provider_manifest(self.provider_factory(role))
            for role in (
                "taxonomy_local",
                "taxonomy_content_type",
                "taxonomy_content_type_global",
                "taxonomy_global",
                "taxonomy_validator",
                "taxonomy_repair",
            )
        }
        if reuse_from_run_id is not None:
            source_run = self.run_repository.get_run(reuse_from_run_id)
            if source_run is None or source_run.get("run_kind") != "full_discovery_run_a":
                raise PipelineError(
                    "复用来源不是 Full Discovery Run A",
                    code="run_a_reuse_source_invalid",
                    retryable=False,
                )
        protocol = {
            "protocol_version": "full-discovery-run-a-v2",
            "snapshot_id": snapshot_id,
            "snapshot_hash": snapshot["snapshot_hash"],
            "snapshot_card_count": snapshot["content_count"],
            "discovery_eligible_count": snapshot["discovery_eligible_count"],
            "trial_assignment_only_count": snapshot["trial_assignment_only_count"],
            "evidence_counts": snapshot["evidence_counts"],
            "profile_run_id": profile_run_id,
            "profile_hash": profile_manifest.get("profiles_hash"),
            "profile_version": "classification_profile_v1",
            "compact_form_view_version": "compact_form_view_v1",
            "domain_prompt_version": LOCAL_TOP_LEVEL_PROMPT_VERSION,
            "content_type_prompt_version": CONTENT_TYPE_PROMPT_VERSION,
            "domain_schema_version": LOCAL_TOP_LEVEL_SCHEMA_VERSION,
            "content_type_schema_version": CONTENT_TYPE_SCHEMA_VERSION,
            "domain_draft_schema_version": TOP_LEVEL_DOMAIN_SCHEMA_VERSION,
            "content_type_draft_schema_version": CONTENT_TYPE_DRAFT_SCHEMA_VERSION,
            "domain_normalization_version": CANDIDATE_NORMALIZATION_VERSION,
            "content_type_normalization_version": CONTENT_TYPE_NORMALIZATION_VERSION,
            "domain_consolidation_prompt_version": TOP_LEVEL_CONSOLIDATION_PROMPT_VERSION,
            "content_type_consolidation_prompt_version": CONTENT_TYPE_CONSOLIDATION_PROMPT_VERSION,
            "quality_gate_version": TOP_LEVEL_QUALITY_GATE_VERSION,
            "providers": providers,
            "temperature": None,
            "batch_size": batch_size,
            "run_seed": seed,
            "ordering_strategy": "stable_short_id_map_then_seeded_shuffle",
            "git_commit": git_commit,
            "git_worktree_clean": True,
            "reuse_from_run_id": reuse_from_run_id,
        }
        run_id = self.create_run(
            snapshot_id=snapshot_id,
            run_kind="full_discovery_run_a",
            seed=seed,
            batch_size=batch_size,
            limit=None,
            representation="classification_profile_v1",
            profile_run_id=profile_run_id,
            selected_ids=selected_ids,
            protocol_manifest=protocol,
        )
        run_dir = self.output_dir / f"run-{run_id:06d}"
        _write_json_once(run_dir / "run-manifest.json", protocol)
        return run_id

    def execute(self, run_id: int, *, resume: bool = False) -> dict[str, Any]:
        try:
            return self._execute_impl(run_id, resume=resume)
        except Exception as exc:
            self._record_workflow_failure(run_id, exc)
            raise

    def _execute_impl(self, run_id: int, *, resume: bool = False) -> dict[str, Any]:
        run = self.run_repository.get_run(run_id)
        if run is None:
            raise LookupError("Taxonomy Run 不存在")
        if run["status"] == "completed":
            return self.status(run_id)
        if run.get("engine_version") != WORKFLOW_ENGINE_VERSION:
            raise PipelineError(
                "未完成的旧 Taxonomy Run 不能跨 Engine 版本恢复；历史产物仍可直接查看",
                code="taxonomy_engine_version_mismatch",
                retryable=False,
            )
        quality_feedback: dict[str, Any] | None = None
        if run["status"] == "quality_failed":
            if not resume:
                return self.status(run_id)
            quality_feedback = self._prepare_quality_retry(run_id)
            run = self.run_repository.get_run(run_id)
            assert run is not None
        elif resume and run["status"] in {"retry_wait", "running"}:
            # A downstream retry can fail after a quality-driven reset. Reload
            # the persisted gate feedback so the retried consolidation prompt
            # retains the exact same input hash across process restarts.
            quality_feedback = self._persisted_quality_feedback(run_id)

        parameters = run["parameters"]
        if run["run_kind"] == "full_discovery_run_a":
            protocol = parameters.get("protocol_manifest")
            run_manifest_path = self.output_dir / f"run-{run_id:06d}" / "run-manifest.json"
            if not protocol or not run_manifest_path.is_file():
                raise PipelineError(
                    "Full Run A 缺少冻结 Manifest",
                    code="run_a_manifest_missing",
                    retryable=False,
                )
            frozen = json.loads(run_manifest_path.read_text(encoding="utf-8"))
            if frozen != protocol:
                raise PipelineError(
                    "Full Run A Manifest 已改变",
                    code="run_a_manifest_changed",
                    retryable=False,
                )
            git_commit, git_clean = _git_state()
            if git_commit != protocol["git_commit"] or not git_clean:
                raise PipelineError(
                    "Full Run A 执行代码或工作区状态与冻结 Manifest 不一致",
                    code="run_a_code_state_changed",
                    retryable=False,
                )
        snapshot = self.snapshot_repository.get_snapshot(int(run["corpus_snapshot_id"]))
        if snapshot is None or snapshot["snapshot_hash"] != parameters["snapshot_hash"]:
            raise PipelineError(
                "Taxonomy Run 的 Snapshot 不存在或 Hash 改变",
                code="taxonomy_snapshot_mismatch",
                retryable=False,
            )
        compact = build_compact_corpus(snapshot["cards"])
        compact_by_id = {str(row[0]): row for row in compact["rows"]}
        selected_ids = parameters.get("selected_ids")
        if selected_ids:
            unknown = set(selected_ids) - set(compact_by_id)
            if unknown:
                raise PipelineError(
                    "Taxonomy Run 的固定短 ID 不属于 Snapshot",
                    code="taxonomy_selected_ids_mismatch",
                    retryable=False,
                )
            eligible = [compact_by_id[str(short_id)] for short_id in selected_ids]
            if any(row[1] == "D" for row in eligible):
                raise PipelineError(
                    "Discovery 固定输入包含 D 级卡片",
                    code="taxonomy_selected_ids_ineligible",
                    retryable=False,
                )
        else:
            eligible = [row for row in compact["rows"] if row[1] != "D"]
        random.Random(int(parameters["seed"])).shuffle(eligible)
        limit = parameters.get("limit")
        if limit is not None:
            eligible = eligible[:int(limit)]
        selected_compact_rows = list(eligible)
        allowed_ids = {str(row[0]) for row in selected_compact_rows}
        representation = str(parameters.get("representation") or "compact")
        if representation == "classification_profile_v1":
            profile_rows = self._load_profile_rows(
                profile_run_id=str(parameters.get("profile_run_id") or ""),
                snapshot_hash=str(parameters["snapshot_hash"]),
                expected_ids=allowed_ids,
            )
            eligible = [profile_rows[str(row[0])] for row in eligible]
        batch_size = int(parameters["batch_size"])
        batches = [
            eligible[index:index + batch_size]
            for index in range(0, len(eligible), batch_size)
        ]
        compact_batches = [
            selected_compact_rows[index:index + batch_size]
            for index in range(0, len(selected_compact_rows), batch_size)
        ]
        run_dir = self.output_dir / f"run-{run_id:06d}"
        run_dir.mkdir(parents=True, exist_ok=True)
        _write_json_once(run_dir / "compact-corpus.json", compact)
        _write_json_once(run_dir / "short-id-map.json", compact["id_map"])
        _write_json_once(
            run_dir / "batch-plan.json",
            {
                "seed": parameters["seed"],
                "batch_size": batch_size,
                "batches": [[row[0] for row in batch] for batch in batches],
            },
        )
        reuse_from_run_id = (parameters.get("protocol_manifest") or {}).get(
            "reuse_from_run_id"
        )
        if reuse_from_run_id is not None:
            self._reuse_discovery_stages(
                run_id=run_id,
                source_run_id=int(reuse_from_run_id),
                run_dir=run_dir,
                domain_batches=batches,
                content_type_batches=compact_batches,
                representation=representation,
            )

        local_outputs: list[LocalTopLevelDiscoveryOutput] = []
        for index, batch in enumerate(batches, start=1):
            prompt = build_top_level_local_prompt(
                batch, representation=representation
            )
            result = self._model_stage(
                run_id=run_id,
                run_dir=run_dir,
                stage_name="local_discovery",
                unit_key=f"batch-{index:03d}",
                role="taxonomy_local",
                prompt=prompt,
                prompt_version=LOCAL_TOP_LEVEL_PROMPT_VERSION,
                schema=LocalTopLevelDiscoveryOutput,
                schema_hint=LOCAL_TOP_LEVEL_SCHEMA_HINT,
                max_tokens=4096,
                input_ids=[row[0] for row in batch],
                validator=lambda value, allowed={row[0] for row in batch}: (
                    validate_local_top_level(value, allowed)
                ),
            )
            local_outputs.append(result)

        local_payload = [value.model_dump(mode="json") for value in local_outputs]
        _write_json(run_dir / "local-candidates.json", local_payload)
        local_content_types: list[ContentTypeDiscoveryOutputV1] = []
        for index, batch in enumerate(compact_batches, start=1):
            result = self._model_stage(
                run_id=run_id,
                run_dir=run_dir,
                stage_name="content_type_discovery",
                unit_key=f"batch-{index:03d}",
                role="taxonomy_content_type",
                prompt=build_content_type_prompt(batch),
                prompt_version=CONTENT_TYPE_PROMPT_VERSION,
                schema=ContentTypeDiscoveryOutputV1,
                schema_hint=CONTENT_TYPE_SCHEMA_HINT,
                max_tokens=4096,
                input_ids=[row[0] for row in batch],
                validator=lambda value, allowed={row[0] for row in batch}: (
                    validate_content_types(value, allowed)
                ),
            )
            local_content_types.append(result)
        _write_json(
            run_dir / "content-type-local-candidates.json",
            [item.model_dump(mode="json") for item in local_content_types],
        )
        content_type_table = self._content_type_normalization_stage(
            run_id=run_id,
            run_dir=run_dir,
            local_outputs=local_content_types,
            allowed_ids=allowed_ids,
        )
        content_type_prompt = build_content_type_consolidation_prompt(
            content_type_table
        )
        if (
            quality_feedback
            and quality_feedback.get("retry_stage") == "content_type_consolidation"
        ):
            content_type_prompt += (
                "\n\n上次质量门禁反馈。只修正这些 Content Type 问题，不改变已验证的其他结构："
                + json.dumps(
                    quality_feedback, ensure_ascii=False, separators=(",", ":")
                )
            )
        content_types = self._model_stage(
            run_id=run_id,
            run_dir=run_dir,
            stage_name="content_type_consolidation",
            unit_key="main",
            role="taxonomy_content_type_global",
            prompt=content_type_prompt,
            prompt_version=CONTENT_TYPE_CONSOLIDATION_PROMPT_VERSION,
            schema=ContentTypeDraftV1,
            schema_hint=CONTENT_TYPE_CONSOLIDATION_SCHEMA_HINT,
            max_tokens=8192,
            input_ids=sorted(
                {
                    short_id
                    for item in content_type_table.content_types
                    for short_id in item.supporting_ids
                }
            ),
            validator=lambda value: validate_content_type_draft(
                value,
                allowed_ids=allowed_ids,
                candidate_ids={
                    item.candidate_id for item in content_type_table.content_types
                },
            ),
        )
        _write_json(run_dir / "content-types.json", content_types.model_dump(mode="json"))
        candidate_table = self._candidate_normalization_stage(
            run_id=run_id,
            run_dir=run_dir,
            local_outputs=local_outputs,
            allowed_ids=allowed_ids,
        )
        consolidation_prompt = build_top_level_consolidation_prompt(candidate_table)
        if quality_feedback and quality_feedback.get("retry_stage") == "consolidation":
            consolidation_prompt += (
                "\n\n上次质量门禁反馈。只修正这些问题，不改变已验证的其他结构："
                + json.dumps(quality_feedback, ensure_ascii=False, separators=(",", ":"))
            )
        draft = self._model_stage(
            run_id=run_id,
            run_dir=run_dir,
            stage_name="consolidation",
            unit_key="main",
            role="taxonomy_global",
            prompt=consolidation_prompt,
            prompt_version=TOP_LEVEL_CONSOLIDATION_PROMPT_VERSION,
            schema=TopLevelDomainDraft,
            schema_hint=TOP_LEVEL_CONSOLIDATION_SCHEMA_HINT,
            max_tokens=8192,
            input_ids=sorted(
                {
                    short_id
                    for item in candidate_table.domains
                    for short_id in item.supporting_ids
                }
            ),
            validator=lambda value: validate_top_level_draft(
                value,
                allowed_ids=allowed_ids,
                candidate_ids={item.candidate_id for item in candidate_table.domains},
            ),
        )
        _write_json(run_dir / "taxonomy-draft.json", draft.model_dump(mode="json"))

        known_entities = _known_entities(selected_compact_rows)
        rules = self._structural_validation_stage(
            run_id=run_id,
            run_dir=run_dir,
            draft=draft,
            candidate_table=candidate_table,
            allowed_ids=allowed_ids,
            known_entity_names=known_entities,
            content_type_names={item.name for item in content_types.content_types},
            content_type_draft=content_types,
            content_type_table=content_type_table,
            local_content_types=local_content_types,
            evidence_by_id={str(row[0]): str(row[1]) for row in selected_compact_rows},
        )
        rows_by_id = {str(row[0]): row for row in eligible}
        validation_reports: list[LocalValidationReport] = []
        for unit in rules.validation_units:
            prompt = build_local_validation_prompt(
                unit=unit, draft=draft, rows_by_id=rows_by_id
            )
            report = self._model_stage(
                run_id=run_id,
                run_dir=run_dir,
                stage_name="local_validation",
                unit_key=unit.unit_id,
                role="taxonomy_validator",
                prompt=prompt,
                prompt_version=LOCAL_VALIDATION_PROMPT_VERSION,
                schema=LocalValidationReport,
                schema_hint=LOCAL_VALIDATION_SCHEMA_HINT,
                max_tokens=2048,
                input_ids=unit.representative_ids,
                validator=lambda value, expected=unit: validate_local_report(value, expected),
            )
            validation_reports.append(report)

        quality = self._top_level_quality_stage(
            run_id=run_id,
            run_dir=run_dir,
            rules=rules,
            reports=validation_reports,
        )
        if not quality.passed:
            self.run_repository.set_run_status(
                run_id,
                "quality_failed",
                current_stage="quality_gate",
                error_code="taxonomy_quality_failed",
                error_message=(
                    quality.blocking_issues[0].message
                    if quality.blocking_issues
                    else "Taxonomy Quality Gate 未通过"
                ),
            )
            return self.status(run_id)

        integrated = DualViewDiscoveryOutputV1(
            domain_input_view=representation,
            domain_draft=draft,
            content_type_draft=content_types,
        )
        _write_json(
            run_dir / "dual-view-discovery-output.json",
            integrated.model_dump(mode="json"),
        )

        self.run_repository.set_run_status(run_id, "completed", current_stage=None)
        return self.status(run_id)

    def _reuse_discovery_stages(
        self,
        *,
        run_id: int,
        source_run_id: int,
        run_dir: Path,
        domain_batches: list[list[Any]],
        content_type_batches: list[list[Any]],
        representation: str,
    ) -> None:
        source_run = self.run_repository.get_run(source_run_id)
        target_run = self.run_repository.get_run(run_id)
        if source_run is None or target_run is None or source_run_id == run_id:
            raise PipelineError(
                "Run A 复用来源不存在或自引用",
                code="run_a_reuse_source_invalid",
                retryable=False,
            )
        source_protocol = source_run["parameters"].get("protocol_manifest") or {}
        target_protocol = target_run["parameters"].get("protocol_manifest") or {}
        comparable_fields = (
            "snapshot_id",
            "snapshot_hash",
            "discovery_eligible_count",
            "evidence_counts",
            "profile_run_id",
            "profile_hash",
            "profile_version",
            "compact_form_view_version",
            "domain_prompt_version",
            "content_type_prompt_version",
            "domain_schema_version",
            "content_type_schema_version",
            "temperature",
            "batch_size",
            "run_seed",
            "ordering_strategy",
        )
        mismatched = [
            field
            for field in comparable_fields
            if source_protocol.get(field) != target_protocol.get(field)
        ]
        for role in ("taxonomy_local", "taxonomy_content_type"):
            if (source_protocol.get("providers") or {}).get(role) != (
                target_protocol.get("providers") or {}
            ).get(role):
                mismatched.append(f"providers.{role}")
        if source_run["parameters"].get("selected_ids") != target_run[
            "parameters"
        ].get("selected_ids"):
            mismatched.append("selected_ids")
        if mismatched:
            raise PipelineError(
                "Run A 批次复用协议不一致：" + ", ".join(mismatched),
                code="run_a_reuse_protocol_mismatch",
                retryable=False,
            )

        source_dir = self.output_dir / f"run-{source_run_id:06d}"
        source_plan_path = source_dir / "batch-plan.json"
        if not source_plan_path.is_file():
            raise PipelineError(
                "Run A 复用来源缺少 batch plan",
                code="run_a_reuse_batch_plan_missing",
                retryable=False,
            )
        source_plan = json.loads(source_plan_path.read_text(encoding="utf-8"))
        expected_batches = [[str(row[0]) for row in batch] for batch in domain_batches]
        if source_plan.get("batches") != expected_batches or [
            [str(row[0]) for row in batch] for batch in content_type_batches
        ] != expected_batches:
            raise PipelineError(
                "Run A 复用来源 Batch 成员或顺序不一致",
                code="run_a_reuse_batch_mismatch",
                retryable=False,
            )

        source_stages = {
            (item["stage_name"], item["unit_key"]): item
            for item in self.run_repository.list_stages(source_run_id)
        }
        lineage_path = run_dir / "reused-discovery-lineage.json"
        existing_lineage = (
            json.loads(lineage_path.read_text(encoding="utf-8"))
            if lineage_path.is_file()
            else {"stages": []}
        )
        existing_by_key = {
            (item["stage_name"], item["unit_key"]): item
            for item in existing_lineage.get("stages") or []
        }
        lineage: list[dict[str, Any]] = []
        specifications = [
            (
                "local_discovery",
                "taxonomy_local",
                LOCAL_TOP_LEVEL_PROMPT_VERSION,
                LocalTopLevelDiscoveryOutput,
                domain_batches,
                lambda batch: build_top_level_local_prompt(
                    batch, representation=representation
                ),
                lambda value, batch: validate_local_top_level(
                    value, {str(row[0]) for row in batch}
                ),
            ),
            (
                "content_type_discovery",
                "taxonomy_content_type",
                CONTENT_TYPE_PROMPT_VERSION,
                ContentTypeDiscoveryOutputV1,
                content_type_batches,
                build_content_type_prompt,
                lambda value, batch: validate_content_types(
                    value, {str(row[0]) for row in batch}
                ),
            ),
        ]
        for (
            stage_name,
            role,
            prompt_version,
            schema,
            batches,
            prompt_builder,
            validator,
        ) in specifications:
            provider = self.provider_factory(role)
            for index, batch in enumerate(batches, start=1):
                unit_key = f"batch-{index:03d}"
                source_stage = source_stages.get((stage_name, unit_key))
                prompt = prompt_builder(batch)
                input_hash = _hash_text(prompt)
                if (
                    source_stage is None
                    or source_stage.get("status") != "completed"
                    or source_stage.get("attempt_count") != 1
                    or source_stage.get("input_hash") != input_hash
                    or source_stage.get("prompt_version") != prompt_version
                    or source_stage.get("model") != provider.model
                    or bool(source_stage.get("thinking_enabled"))
                    != bool(provider.thinking_enabled)
                    or source_stage.get("reasoning_effort")
                    != provider.reasoning_effort
                ):
                    raise PipelineError(
                        f"Run A 复用资格检查失败：{stage_name}/{unit_key}",
                        code="run_a_reuse_stage_mismatch",
                        retryable=False,
                    )
                source_output = Path(str(source_stage.get("output_path") or ""))
                source_call_dir = source_output.parent
                source_prompt = source_call_dir / "prompt.txt"
                source_raw = source_call_dir / "raw-response.txt"
                source_audit = source_call_dir / "audit.json"
                if not all(
                    path.is_file()
                    for path in (source_output, source_prompt, source_raw, source_audit)
                ) or source_prompt.read_text(encoding="utf-8") != prompt:
                    raise PipelineError(
                        f"Run A 复用来源产物不完整：{stage_name}/{unit_key}",
                        code="run_a_reuse_artifact_invalid",
                        retryable=False,
                    )
                audit = json.loads(source_audit.read_text(encoding="utf-8"))
                expected_ids = [str(row[0]) for row in batch]
                expected_provider = (target_protocol.get("providers") or {}).get(role)
                if (
                    audit.get("status") != "completed"
                    or audit.get("prompt_version") != prompt_version
                    or audit.get("model") != provider.model
                    or audit.get("input_ids") != expected_ids
                    or audit.get("request_attempt_count") != 1
                    or audit.get("repair") is not None
                    or (audit.get("parameters") or {}).get("thinking_enabled")
                    != provider.thinking_enabled
                    or (audit.get("parameters") or {}).get("reasoning_effort")
                    != provider.reasoning_effort
                ):
                    raise PipelineError(
                        f"Run A 复用来源 Audit 不匹配：{stage_name}/{unit_key}",
                        code="run_a_reuse_audit_mismatch",
                        retryable=False,
                    )
                parsed = schema.model_validate_json(
                    source_output.read_text(encoding="utf-8")
                )
                validator(parsed, batch)
                output_hash = _stable_hash(parsed.model_dump(mode="json"))
                if output_hash != source_stage.get("output_hash"):
                    raise PipelineError(
                        f"Run A 复用来源输出 Hash 不匹配：{stage_name}/{unit_key}",
                        code="run_a_reuse_output_hash_mismatch",
                        retryable=False,
                    )
                target_call_dir = (
                    run_dir / stage_name / unit_key / "reused-attempt-00"
                )
                if not target_call_dir.exists():
                    target_call_dir.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(source_call_dir, target_call_dir)
                target_output = target_call_dir / "parsed-output.json"
                if _hash_file(target_output) != _hash_file(source_output):
                    raise PipelineError(
                        "复制后的复用产物 Hash 改变",
                        code="run_a_reuse_copy_hash_mismatch",
                        retryable=False,
                    )
                existing = existing_by_key.get((stage_name, unit_key))
                record = {
                    "stage_name": stage_name,
                    "unit_key": unit_key,
                    "batch_members": [str(row[0]) for row in batch],
                    "reused_from_run_id": source_run_id,
                    "reused_from_stage_id": int(source_stage["id"]),
                    "source_input_hash": input_hash,
                    "source_output_hash": output_hash,
                    "source_raw_hash": _hash_file(source_raw),
                    "source_parsed_file_hash": _hash_file(source_output),
                    "source_prompt_file_hash": _hash_file(source_prompt),
                    "source_audit_hash": _hash_file(source_audit),
                    "prompt_version": prompt_version,
                    "provider_contract": expected_provider,
                    "model": provider.model,
                    "thinking_enabled": provider.thinking_enabled,
                    "reasoning_effort": provider.reasoning_effort,
                    "reuse_reason": (
                        "模型输入、输出语义与冻结协议未改变；仅修复下游容量和失败状态"
                    ),
                    "verified_at": (
                        existing.get("verified_at") if existing else _utc_now()
                    ),
                }
                if existing is not None and existing != record:
                    raise PipelineError(
                        "Run A 复用血缘在 Resume 时改变",
                        code="run_a_reuse_lineage_changed",
                        retryable=False,
                    )
                lineage.append(record)
                self.run_repository.record_reused_stage(
                    run_id,
                    stage_name,
                    unit_key,
                    input_hash=input_hash,
                    output_path=str(target_output),
                    output_hash=output_hash,
                    model=provider.model,
                    prompt_version=prompt_version,
                    thinking_enabled=provider.thinking_enabled,
                    reasoning_effort=provider.reasoning_effort,
                )
        _write_json_once(
            lineage_path,
            {
                "source_run_id": source_run_id,
                "target_run_id": run_id,
                "reused_stage_count": len(lineage),
                "stages": lineage,
            },
        )

    def _record_workflow_failure(self, run_id: int, exc: Exception) -> None:
        run = self.run_repository.get_run(run_id)
        if run is None or run.get("status") in {"completed", "quality_failed"}:
            return
        stages = self.run_repository.list_stages(run_id)
        failed_stage = str(run.get("current_stage") or "workflow")
        retryable = isinstance(exc, PipelineError) and exc.retryable
        error_code = (
            exc.code if isinstance(exc, PipelineError) else "taxonomy_unhandled_exception"
        )
        current = next(
            (
                item
                for item in stages
                if item["stage_name"] == failed_stage
                and item["status"] in {"pending", "processing"}
            ),
            None,
        )
        if current is not None:
            self.run_repository.fail_stage(
                run_id,
                current["stage_name"],
                current["unit_key"],
                error_code=error_code,
                error_message=str(exc),
                retryable=retryable,
            )
        elif run.get("status") not in {"failed", "retry_wait"}:
            self.run_repository.set_run_status(
                run_id,
                "retry_wait" if retryable else "failed",
                current_stage=failed_stage,
                error_code=error_code,
                error_message=str(exc),
            )
        refreshed = self.run_repository.list_stages(run_id)
        completed = [
            f"{item['stage_name']}/{item['unit_key']}"
            for item in refreshed
            if item["status"] == "completed"
        ]
        unfinished = [
            f"{item['stage_name']}/{item['unit_key']}"
            for item in refreshed
            if item["status"] != "completed"
        ]
        _write_json(
            self.output_dir / f"run-{run_id:06d}" / "run-failure.json",
            {
                "run_id": run_id,
                "failed_stage": failed_stage,
                "failed_at": _utc_now(),
                "last_error": {"code": error_code, "message": str(exc)},
                "retryable": retryable,
                "completed_stages": completed,
                "unfinished_stages": unfinished,
                "allows_model_artifact_reuse": bool(
                    completed
                    and all(
                        item["status"] == "completed"
                        for item in refreshed
                        if item["stage_name"]
                        in {"local_discovery", "content_type_discovery"}
                    )
                ),
            },
        )

    def _load_profile_rows(
        self,
        *,
        profile_run_id: str,
        snapshot_hash: str,
        expected_ids: set[str],
    ) -> dict[str, list[Any]]:
        if self.profile_output_dir is None:
            raise PipelineError(
                "Taxonomy Workflow 未配置 Profile 私有目录",
                code="taxonomy_profile_dir_missing",
                retryable=False,
            )
        run_dir = self.profile_output_dir / profile_run_id
        self._accepted_profile_manifest(
            profile_run_id=profile_run_id,
            snapshot_hash=snapshot_hash,
        )
        rows_path = run_dir / "profile-discovery-view.jsonl"
        if not rows_path.is_file():
            raise PipelineError(
                "Classification Profile Run 不存在或产物不完整",
                code="taxonomy_profile_run_missing",
                retryable=False,
            )
        rows = [
            json.loads(line)
            for line in rows_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        by_id = {str(row[0]): row for row in rows}
        if len(by_id) != len(rows) or set(by_id) != expected_ids:
            raise PipelineError(
                "Classification Profile IDs 与配对输入不一致",
                code="taxonomy_profile_ids_mismatch",
                retryable=False,
            )
        return by_id

    def _accepted_profile_manifest(
        self, *, profile_run_id: str, snapshot_hash: str
    ) -> dict[str, Any]:
        if self.profile_output_dir is None:
            raise PipelineError(
                "Taxonomy Workflow 未配置 Profile 私有目录",
                code="taxonomy_profile_dir_missing",
                retryable=False,
            )
        manifest_path = self.profile_output_dir / profile_run_id / "manifest.json"
        if not manifest_path.is_file():
            raise PipelineError(
                "Classification Profile Run 不存在或产物不完整",
                code="taxonomy_profile_run_missing",
                retryable=False,
            )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            manifest.get("status") != "completed"
            or manifest.get("snapshot_hash") != snapshot_hash
            or manifest.get("profile_version") != "classification_profile_v1"
            or manifest.get("prompt_version") != "classification-profile-generation-v2"
            or not manifest.get("gates")
            or not all(manifest["gates"].values())
        ):
            raise PipelineError(
                "Classification Profile Run 未通过 3.7A 或 Snapshot 不匹配",
                code="taxonomy_profile_run_unaccepted",
                retryable=False,
            )
        return manifest

    def _model_stage(
        self,
        *,
        run_id: int,
        run_dir: Path,
        stage_name: str,
        unit_key: str,
        role: str,
        prompt: str,
        prompt_version: str,
        schema: type[SchemaT],
        schema_hint: str,
        max_tokens: int,
        input_ids: list[str],
        validator,
    ) -> SchemaT:
        input_hash = _hash_text(prompt)
        stage = self.run_repository.ensure_stage(
            run_id, stage_name, unit_key, input_hash=input_hash
        )
        if stage["status"] == "completed":
            return _load_completed(stage, schema, validator)
        if stage["status"] == "failed":
            raise PipelineError(
                str(stage.get("last_error_message") or "Taxonomy Stage 不可重试"),
                code=str(stage.get("last_error_code") or "taxonomy_stage_failed"),
                retryable=False,
            )
        previous_attempt = int(stage["attempt_count"])
        resume_existing = stage["status"] in {"processing", "retry_wait"} and previous_attempt > 0
        provider = self.provider_factory(role)
        repair_provider = self.provider_factory("taxonomy_repair")
        started = self.run_repository.start_stage(
            run_id,
            stage_name,
            unit_key,
            input_hash=input_hash,
            model=provider.model,
            prompt_version=prompt_version,
            thinking_enabled=provider.thinking_enabled,
            reasoning_effort=provider.reasoning_effort,
        )
        attempt_number = previous_attempt if resume_existing else int(started["attempt_count"])
        call_dir = run_dir / stage_name / unit_key / f"attempt-{attempt_number:02d}"
        caller = AuditedJsonCaller(provider=provider, repair_provider=repair_provider)
        try:
            result, audit = caller.call(
                call_dir=call_dir,
                prompt=prompt,
                prompt_version=prompt_version,
                schema=schema,
                schema_hint=schema_hint,
                max_tokens=max_tokens,
                input_ids=input_ids,
                validator=validator,
                resume=call_dir.exists(),
            )
        except PipelineError as exc:
            self.run_repository.fail_stage(
                run_id,
                stage_name,
                unit_key,
                error_code=exc.code,
                error_message=str(exc),
                retryable=exc.retryable,
            )
            raise
        output = result.model_dump(mode="json")
        output_path = call_dir / "parsed-output.json"
        stage_audit = _combined_audit(audit)
        self.run_repository.complete_stage(
            run_id,
            stage_name,
            unit_key,
            output_path=str(output_path),
            output_hash=_stable_hash(output),
            audit=stage_audit,
        )
        return result

    def _candidate_normalization_stage(
        self,
        *,
        run_id: int,
        run_dir: Path,
        local_outputs: list[LocalTopLevelDiscoveryOutput],
        allowed_ids: set[str],
    ) -> CompactCandidateTable:
        input_value = [item.model_dump(mode="json") for item in local_outputs]
        input_hash = _stable_hash(input_value)
        stage = self.run_repository.ensure_stage(
            run_id, "candidate_normalization", "main", input_hash=input_hash
        )
        if stage["status"] == "completed":
            return _load_completed(stage, CompactCandidateTable, None)
        self.run_repository.start_stage(
            run_id,
            "candidate_normalization",
            "main",
            input_hash=input_hash,
            model=None,
            prompt_version=CANDIDATE_NORMALIZATION_VERSION,
            thinking_enabled=None,
            reasoning_effort=None,
        )
        result = normalize_candidates(local_outputs, allowed_ids=allowed_ids)
        output_path = run_dir / "candidate-normalization" / "compact-candidates.json"
        _write_json(output_path, result.model_dump(mode="json"))
        self.run_repository.complete_stage(
            run_id,
            "candidate_normalization",
            "main",
            output_path=str(output_path),
            output_hash=_stable_hash(result.model_dump(mode="json")),
        )
        return result

    def _content_type_normalization_stage(
        self,
        *,
        run_id: int,
        run_dir: Path,
        local_outputs: list[ContentTypeDiscoveryOutputV1],
        allowed_ids: set[str],
    ) -> CompactContentTypeTable:
        input_value = [item.model_dump(mode="json") for item in local_outputs]
        input_hash = _stable_hash(input_value)
        stage = self.run_repository.ensure_stage(
            run_id, "content_type_normalization", "main", input_hash=input_hash
        )
        if stage["status"] == "completed":
            return _load_completed(stage, CompactContentTypeTable, None)
        self.run_repository.start_stage(
            run_id,
            "content_type_normalization",
            "main",
            input_hash=input_hash,
            model=None,
            prompt_version=CONTENT_TYPE_NORMALIZATION_VERSION,
            thinking_enabled=None,
            reasoning_effort=None,
        )
        result = normalize_content_types(local_outputs, allowed_ids=allowed_ids)
        output_path = (
            run_dir / "content-type-normalization" / "compact-content-types.json"
        )
        _write_json(output_path, result.model_dump(mode="json"))
        self.run_repository.complete_stage(
            run_id,
            "content_type_normalization",
            "main",
            output_path=str(output_path),
            output_hash=_stable_hash(result.model_dump(mode="json")),
        )
        return result

    def _structural_validation_stage(
        self,
        *,
        run_id: int,
        run_dir: Path,
        draft: TopLevelDomainDraft,
        candidate_table: CompactCandidateTable,
        allowed_ids: set[str],
        known_entity_names: set[str],
        content_type_names: set[str],
        content_type_draft: ContentTypeDraftV1,
        content_type_table: CompactContentTypeTable,
        local_content_types: list[ContentTypeDiscoveryOutputV1],
        evidence_by_id: dict[str, str],
    ) -> TopLevelRuleResult:
        input_value = {
            "draft": draft.model_dump(mode="json"),
            "candidates": candidate_table.model_dump(mode="json"),
            "known_entities": sorted(known_entity_names),
            "content_types": sorted(content_type_names),
            "content_type_draft": content_type_draft.model_dump(mode="json"),
            "content_type_candidates": content_type_table.model_dump(mode="json"),
            "local_content_types": [
                item.model_dump(mode="json") for item in local_content_types
            ],
            "evidence_by_id": evidence_by_id,
        }
        input_hash = _stable_hash(input_value)
        stage = self.run_repository.ensure_stage(
            run_id, "structural_validation", "main", input_hash=input_hash
        )
        if stage["status"] == "completed":
            return _load_completed(stage, TopLevelRuleResult, None)
        self.run_repository.start_stage(
            run_id,
            "structural_validation",
            "main",
            input_hash=input_hash,
            model=None,
            prompt_version="deterministic-top-level-validation-v1",
            thinking_enabled=None,
            reasoning_effort=None,
        )
        result = evaluate_top_level_rules(
            draft=draft,
            candidate_table=candidate_table,
            allowed_ids=allowed_ids,
            known_entity_names=known_entity_names,
            content_type_names=content_type_names,
            content_type_draft=content_type_draft,
            content_type_table=content_type_table,
            local_content_types=local_content_types,
            evidence_by_id=evidence_by_id,
        )
        output_path = run_dir / "structural-validation" / "validation-plan.json"
        _write_json(output_path, result.model_dump(mode="json"))
        self.run_repository.complete_stage(
            run_id,
            "structural_validation",
            "main",
            output_path=str(output_path),
            output_hash=_stable_hash(result.model_dump(mode="json")),
        )
        return result

    def _top_level_quality_stage(
        self,
        *,
        run_id: int,
        run_dir: Path,
        rules: TopLevelRuleResult,
        reports: list[LocalValidationReport],
    ) -> TopLevelQualityResult:
        input_value = {
            "rules": rules.model_dump(mode="json"),
            "reports": [item.model_dump(mode="json") for item in reports],
        }
        input_hash = _stable_hash(input_value)
        stage = self.run_repository.ensure_stage(
            run_id, "quality_gate", "main", input_hash=input_hash
        )
        if stage["status"] == "completed":
            return _load_completed(stage, TopLevelQualityResult, None)
        self.run_repository.start_stage(
            run_id,
            "quality_gate",
            "main",
            input_hash=input_hash,
            model=None,
            prompt_version=TOP_LEVEL_QUALITY_GATE_VERSION,
            thinking_enabled=None,
            reasoning_effort=None,
        )
        result = combine_top_level_quality(rules=rules, reports=reports)
        output_path = run_dir / "quality-gate" / "quality-result.json"
        _write_json(output_path, result.model_dump(mode="json"))
        self.run_repository.complete_stage(
            run_id,
            "quality_gate",
            "main",
            output_path=str(output_path),
            output_hash=_stable_hash(result.model_dump(mode="json")),
        )
        return result

    def _prepare_quality_retry(self, run_id: int) -> dict[str, Any]:
        stages = self.run_repository.list_stages(run_id)
        quality_stage = next(
            (item for item in stages if item["stage_name"] == "quality_gate"), None
        )
        if quality_stage is None or not quality_stage.get("output_path"):
            raise PipelineError(
                "quality_failed Run 缺少 Quality Gate 产物",
                code="taxonomy_resume_corrupt",
                retryable=False,
            )
        feedback = json.loads(
            Path(str(quality_stage["output_path"])).read_text(encoding="utf-8")
        )
        retry_stage = feedback.get("retry_stage")
        reset = {
            "consolidation": [
                "consolidation", "structural_validation", "local_validation",
                "quality_gate",
            ],
            "content_type_consolidation": [
                "content_type_consolidation", "structural_validation",
                "local_validation", "quality_gate",
            ],
            "local_validation": [
                "local_validation", "quality_gate",
            ],
        }.get(retry_stage)
        if reset is None:
            raise PipelineError(
                "Quality Gate 没有可恢复的 retry_stage",
                code="taxonomy_quality_no_retry",
                retryable=False,
            )
        self.run_repository.reset_stages(run_id, reset)
        return feedback

    def _persisted_quality_feedback(self, run_id: int) -> dict[str, Any] | None:
        path = (
            self.output_dir
            / f"run-{run_id:06d}"
            / "quality-gate"
            / "quality-result.json"
        )
        if not path.is_file():
            return None
        feedback = json.loads(path.read_text(encoding="utf-8"))
        return feedback if feedback.get("passed") is False else None


def _load_completed(stage: dict[str, Any], schema: type[SchemaT], validator) -> SchemaT:
    path = Path(str(stage.get("output_path") or ""))
    if not path.is_file():
        raise PipelineError(
            "已完成 Stage 的输出文件不存在",
            code="taxonomy_resume_corrupt",
            retryable=False,
        )
    result = schema.model_validate_json(path.read_text(encoding="utf-8"))
    if _stable_hash(result.model_dump(mode="json")) != stage.get("output_hash"):
        raise PipelineError(
            "已完成 Stage 的输出 Hash 不匹配",
            code="taxonomy_resume_corrupt",
            retryable=False,
        )
    if validator:
        validator(result)
    return result


def _known_entities(rows: list[list[Any]]) -> set[str]:
    result: set[str] = set()
    for row in rows:
        if len(row) >= 6 and row[1] in {"A", "B"}:
            result.update(str(value) for value in row[5] if str(value).strip())
    return result


def _combined_audit(audit: dict[str, Any]) -> dict[str, Any]:
    repair = audit.get("repair") or {}
    attempts = [audit, *(audit.get("attempt_history") or [])]
    repair_attempts = [repair, *(repair.get("attempt_history") or [])]
    usage_values = [
        item.get("usage") or {}
        for item in [*attempts, *repair_attempts]
    ]
    numeric_keys = {
        key for usage in usage_values for key, value in usage.items()
        if isinstance(value, (int, float))
    }
    usage = {
        key: sum(value for source in usage_values if isinstance((value := source.get(key)), (int, float)))
        for key in numeric_keys
    }
    reasoning_values = [
        details.get("reasoning_tokens")
        for source in usage_values
        if isinstance((details := source.get("completion_tokens_details")), dict)
    ]
    cached_values = [
        details.get("cached_tokens")
        for source in usage_values
        if isinstance((details := source.get("prompt_tokens_details")), dict)
    ]
    if any(isinstance(value, (int, float)) for value in reasoning_values):
        usage["completion_tokens_details"] = {
            "reasoning_tokens": sum(
                value for value in reasoning_values if isinstance(value, (int, float))
            )
        }
    if any(isinstance(value, (int, float)) for value in cached_values):
        usage["prompt_tokens_details"] = {
            "cached_tokens": sum(
                value for value in cached_values if isinstance(value, (int, float))
            )
        }
    return {
        **audit,
        "usage": usage or None,
        "elapsed_seconds": sum(
            item.get("elapsed_seconds") or 0
            for item in [*attempts, *repair_attempts]
        ),
    }


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _stable_hash(value: Any) -> str:
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


def _write_json_once(path: Path, value: Any) -> None:
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != value:
            raise PipelineError(
                "Run 冻结输入与恢复输入不一致",
                code="taxonomy_resume_input_mismatch",
                retryable=False,
            )
        return
    _write_json(path, value)


def _git_state() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[3]
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return commit, not bool(status.strip())


def _provider_manifest(provider: OpenAICompatibleProvider) -> dict[str, Any]:
    return {
        "provider": getattr(provider, "name", "openai-compatible"),
        "model": provider.model,
        "thinking_enabled": provider.thinking_enabled,
        "reasoning_effort": provider.reasoning_effort,
        "temperature": None,
    }
