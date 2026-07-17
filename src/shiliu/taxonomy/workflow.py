from __future__ import annotations

import hashlib
import json
import random
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
    LOCAL_TOP_LEVEL_PROMPT_VERSION,
    LOCAL_TOP_LEVEL_SCHEMA_HINT,
    TOP_LEVEL_CONSOLIDATION_PROMPT_VERSION,
    TOP_LEVEL_CONSOLIDATION_SCHEMA_HINT,
    CompactCandidateTable,
    LocalTopLevelDiscoveryOutput,
    TopLevelDomainDraft,
    build_top_level_consolidation_prompt,
    build_top_level_local_prompt,
    normalize_candidates,
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
    build_local_validation_prompt,
    combine_top_level_quality,
    evaluate_top_level_rules,
    validate_local_report,
)
from shiliu.taxonomy.repository import TaxonomyRepository
from shiliu.taxonomy.run_repository import TaxonomyRunRepository


SchemaT = TypeVar("SchemaT", bound=BaseModel)
WORKFLOW_ENGINE_VERSION = "top-level-cost-bounded-workflow-v2"


class TaxonomyWorkflow:
    """Minimal database-backed runner for regression and later A/B/C discovery runs."""

    def __init__(
        self,
        *,
        snapshot_repository: TaxonomyRepository,
        run_repository: TaxonomyRunRepository,
        provider_factory: Callable[[str], OpenAICompatibleProvider],
        output_dir: Path,
    ) -> None:
        self.snapshot_repository = snapshot_repository
        self.run_repository = run_repository
        self.provider_factory = provider_factory
        self.output_dir = output_dir

    def create_run(
        self,
        *,
        snapshot_id: int,
        run_kind: str = "regression",
        seed: int = 73,
        batch_size: int = 24,
        limit: int | None = 48,
        include_assignment: bool = False,
    ) -> int:
        if not 20 <= batch_size <= 32:
            raise ValueError("Taxonomy batch_size must be between 20 and 32")
        if include_assignment:
            raise ValueError("Checkpoint 3.5 尚未开放一级 Trial Assignment")
        snapshot = self.snapshot_repository.get_snapshot(snapshot_id)
        if snapshot is None:
            raise LookupError("快照不存在")
        parameters = {
            "snapshot_hash": snapshot["snapshot_hash"],
            "seed": seed,
            "batch_size": batch_size,
            "limit": limit,
            "include_assignment": include_assignment,
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

    def execute(self, run_id: int, *, resume: bool = False) -> dict[str, Any]:
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
        snapshot = self.snapshot_repository.get_snapshot(int(run["corpus_snapshot_id"]))
        if snapshot is None or snapshot["snapshot_hash"] != parameters["snapshot_hash"]:
            raise PipelineError(
                "Taxonomy Run 的 Snapshot 不存在或 Hash 改变",
                code="taxonomy_snapshot_mismatch",
                retryable=False,
            )
        compact = build_compact_corpus(snapshot["cards"])
        eligible = [row for row in compact["rows"] if row[1] != "D"]
        random.Random(int(parameters["seed"])).shuffle(eligible)
        limit = parameters.get("limit")
        if limit is not None:
            eligible = eligible[:int(limit)]
        batch_size = int(parameters["batch_size"])
        batches = [
            eligible[index:index + batch_size]
            for index in range(0, len(eligible), batch_size)
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

        local_outputs: list[LocalTopLevelDiscoveryOutput] = []
        for index, batch in enumerate(batches, start=1):
            prompt = build_top_level_local_prompt(batch)
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
        candidate_table = self._candidate_normalization_stage(
            run_id=run_id,
            run_dir=run_dir,
            local_outputs=local_outputs,
            allowed_ids=set(compact["id_map"]),
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
                value, allowed_ids=set(compact["id_map"])
            ),
        )
        _write_json(run_dir / "taxonomy-draft.json", draft.model_dump(mode="json"))

        known_entities = _known_entities(compact["rows"])
        rules = self._structural_validation_stage(
            run_id=run_id,
            run_dir=run_dir,
            draft=draft,
            candidate_table=candidate_table,
            allowed_ids=set(compact["id_map"]),
            known_entity_names=known_entities,
        )
        rows_by_id = {str(row[0]): row for row in compact["rows"]}
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

        self.run_repository.set_run_status(run_id, "completed", current_stage=None)
        return self.status(run_id)

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

    def _structural_validation_stage(
        self,
        *,
        run_id: int,
        run_dir: Path,
        draft: TopLevelDomainDraft,
        candidate_table: CompactCandidateTable,
        allowed_ids: set[str],
        known_entity_names: set[str],
    ) -> TopLevelRuleResult:
        input_value = {
            "draft": draft.model_dump(mode="json"),
            "candidates": candidate_table.model_dump(mode="json"),
            "known_entities": sorted(known_entity_names),
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
            prompt_version="top-level-quality-gate-v1",
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
