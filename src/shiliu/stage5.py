from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from typing import Any, Callable, Literal

from pydantic import ConfigDict

from shiliu.artifacts import ArtifactStore
from shiliu.db import Database
from shiliu.evidence import (
    EvidenceContractError,
    EvidenceSearchService,
    SourceArtifactReference,
    load_source_artifact,
)
from shiliu.evidence.contracts import SearchCandidateSet
from shiliu.evidence.stage3a import (
    CANDIDATE_GENERATION_POLICY_STAGE3B,
    DETERMINISTIC_SELECTOR_VERSION,
    CandidateBuilderConfig,
    EvidenceBundle,
    EvidenceCandidateSet,
    SelectorConfig,
    resolve_from_search_candidates,
    select_deterministic_bundle,
    validate_bundle,
)
from shiliu.evidence.stage4 import (
    FINAL_CANDIDATE_BUILDER_VERSION,
    MECHANICAL_GATE_CONTRACT_VERSION,
    MECHANICAL_GATE_POLICY_VERSION,
    SUFFICIENCY_REQUEST_CONTRACT_VERSION,
    EvidenceResolutionState,
    MechanicalGateDecision,
    MechanicalGatePolicy,
    SufficiencyDecision,
    SufficiencyRequest,
    apply_mechanical_sufficiency_gate,
    canonical_bytes,
    stable_id,
)
from shiliu.eval_v3_5.stage4b import (
    SEMANTIC_JUDGE_CONTRACT_VERSION,
    SEMANTIC_POLICY_VERSION,
    SEMANTIC_PROMPT_VERSION,
    SemanticJudgeBatchOutput,
    batch_prompt,
    parse_batch_output,
    project_runtime_request,
    to_decision,
    validate_output,
)
from shiliu.retrieval.product_search import ProductSearchRequest


STAGE5_PIPELINE_VERSION = "v3.5-stage5-minimal-integration-v1"
STAGE5_TRACE_CONTRACT_VERSION = "v3.5-stage5-root-trace-v1"
SEMANTIC_JUDGE_PROVIDER = "openai-codex-cli"
SEMANTIC_JUDGE_MODEL = "gpt-5.6-terra"
SEMANTIC_JUDGE_TEMPERATURE = 0
SEMANTIC_JUDGE_REASONING_EFFORT = "medium"
SEMANTIC_JUDGE_MAX_RETRIES = 1
SEMANTIC_JUDGE_MAX_OBSERVED_LATENCY_MS = 89173
SEMANTIC_JUDGE_TIMEOUT_SECONDS = 180


class Stage5PipelineRequest(ProductSearchRequest):
    model_config = ConfigDict(extra="forbid")

    query_language: str = "und"

    def search_request(self) -> ProductSearchRequest:
        return ProductSearchRequest.model_validate(
            self.model_dump(exclude={"query_language"})
        )


class Stage5IntegrationError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_type: str,
        stage: str,
        retry_count: int = 0,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.stage = stage
        self.retry_count = retry_count

    def as_dict(self) -> dict[str, object]:
        return {
            "type": self.error_type,
            "stage": self.stage,
            "message": str(self)[:500],
            "retry_count": self.retry_count,
        }


class FrozenSemanticJudgeAdapter:
    """Thin runtime transport for the frozen Stage 4B Codex judge."""

    provider = SEMANTIC_JUDGE_PROVIDER
    model = SEMANTIC_JUDGE_MODEL
    temperature = SEMANTIC_JUDGE_TEMPERATURE
    prompt_version = SEMANTIC_PROMPT_VERSION
    policy_version = SEMANTIC_POLICY_VERSION

    def __init__(
        self,
        *,
        timeout_seconds: int = SEMANTIC_JUDGE_TIMEOUT_SECONDS,
        runner: Callable[[str, Path, int], str] | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.runner = runner or self._run_codex

    def judge(
        self,
        request: SufficiencyRequest,
        bundle: EvidenceBundle,
    ) -> tuple[SufficiencyDecision, dict[str, object]]:
        prompt = batch_prompt((request,))
        last_error: Exception | None = None
        total_latency_ms = 0
        for attempt in range(SEMANTIC_JUDGE_MAX_RETRIES + 1):
            started = time.perf_counter()
            try:
                with tempfile.TemporaryDirectory(prefix="shiliu-stage5-judge-") as temp:
                    schema_path = Path(temp) / "semantic-judge-output.schema.json"
                    schema_path.write_text(
                        json.dumps(
                            SemanticJudgeBatchOutput.model_json_schema(),
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        encoding="utf-8",
                    )
                    raw = self.runner(prompt, schema_path, self.timeout_seconds)
                total_latency_ms += _elapsed_ms(started)
                output = parse_batch_output(raw, 1)[0]
                validate_output(output, request, bundle)
                return (
                    to_decision(output, request, bundle, judge_model=self.model),
                    {
                        "provider": self.provider,
                        "model": self.model,
                        "temperature": self.temperature,
                        "prompt_version": self.prompt_version,
                        "policy_version": self.policy_version,
                        "parse_status": "valid",
                        "raw_response_hash": sha256(raw.encode("utf-8")).hexdigest(),
                        "latency_ms": total_latency_ms,
                        "retry_count": attempt,
                    },
                )
            except subprocess.TimeoutExpired as exc:
                total_latency_ms += _elapsed_ms(started)
                last_error = exc
                error_type = "judge_timeout_or_provider_error"
            except (json.JSONDecodeError, ValueError) as exc:
                total_latency_ms += _elapsed_ms(started)
                last_error = exc
                error_type = "structured_output_error"
                prompt = (
                    batch_prompt((request,))
                    + "\n\nMECHANICAL REPAIR: The prior output failed validation: "
                    + str(exc)
                    + ". Preserve your semantic status decision, but for evidence_ids_used copy only "
                    "exact full strings from that same item's evidence_bundle.candidate_ids. Never use "
                    "span_id, segment_id, shortened IDs, or IDs from another item."
                )
            except Stage5IntegrationError as exc:
                total_latency_ms += _elapsed_ms(started)
                last_error = exc
                error_type = exc.error_type
            except Exception as exc:
                total_latency_ms += _elapsed_ms(started)
                last_error = exc
                error_type = "judge_timeout_or_provider_error"
        raise Stage5IntegrationError(
            f"{type(last_error).__name__}: {last_error}",
            error_type=error_type,
            stage="semantic_judge",
            retry_count=SEMANTIC_JUDGE_MAX_RETRIES,
        )

    @staticmethod
    def _run_codex(prompt: str, schema_path: Path, timeout_seconds: int) -> str:
        executable = _resolve_codex_executable()
        if executable is None:
            raise Stage5IntegrationError(
                "codex executable unavailable",
                error_type="judge_timeout_or_provider_error",
                stage="semantic_judge",
            )
        output_path = schema_path.parent / "last-message.json"
        command = [
            executable,
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "-m",
            SEMANTIC_JUDGE_MODEL,
            "-c",
            f'model_reasoning_effort="{SEMANTIC_JUDGE_REASONING_EFFORT}"',
            "-c",
            f"model_temperature={SEMANTIC_JUDGE_TEMPERATURE}",
            "-s",
            "read-only",
            "-C",
            str(schema_path.parent),
            "--skip-git-repo-check",
            "--output-schema",
            str(schema_path),
            "-o",
            str(output_path),
            "-",
        ]
        completed = subprocess.run(
            command,
            input=prompt,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
        if completed.returncode != 0 or not output_path.is_file():
            detail = (completed.stderr or completed.stdout)[-2000:]
            raise Stage5IntegrationError(
                f"semantic judge provider failed: {detail}",
                error_type="judge_timeout_or_provider_error",
                stage="semantic_judge",
            )
        return output_path.read_text(encoding="utf-8")


def _resolve_codex_executable() -> str | None:
    configured = os.environ.get("SHILIU_CODEX_EXECUTABLE")
    candidates = [
        configured,
        shutil.which("codex"),
        "/Applications/ChatGPT.app/Contents/Resources/codex",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


class Stage5PipelineService:
    def __init__(
        self,
        *,
        db: Database,
        artifacts: ArtifactStore,
        evidence_search: EvidenceSearchService,
        trace_dir: Path,
        judge: FrozenSemanticJudgeAdapter | None = None,
    ) -> None:
        self.db = db
        self.artifacts = artifacts
        self.evidence_search = evidence_search
        self.trace_dir = trace_dir
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self.judge = judge or FrozenSemanticJudgeAdapter()
        self.builder_config = CandidateBuilderConfig(
            config_id=FINAL_CANDIDATE_BUILDER_VERSION,
            within_video_max_candidates=32,
            candidate_generation_policy_version=CANDIDATE_GENERATION_POLICY_STAGE3B,
            asr_acronym_anchor_enabled=True,
            acronym_anchor_weight=3.5,
            adaptive_coverage_swap_enabled=False,
        )
        self.selector_config = SelectorConfig()
        self.gate_policy = MechanicalGatePolicy()

    def run(self, request: Stage5PipelineRequest) -> dict[str, object]:
        started = time.perf_counter()
        started_at = _utc_now()
        request_id = stable_id(
            "stage5_request_",
            {
                "pipeline": STAGE5_PIPELINE_VERSION,
                "request": request.model_dump(mode="json"),
                "started_at": started_at,
            },
        )
        trace_id = stable_id(
            "stage5_trace_",
            {"request_id": request_id, "query_hash": _hash(request.query)},
        )
        trace: dict[str, object] = {
            "trace_contract_version": STAGE5_TRACE_CONTRACT_VERSION,
            "trace_id": trace_id,
            "request_id": request_id,
            "query_hash": _hash(request.query),
            "started_at": started_at,
            "completed_at": None,
            "total_latency_ms": None,
            "final_pipeline_status": "processing",
            "stages": [],
        }
        response = self._base_response(request, request_id, trace_id)
        try:
            search_set = self._stage(
                trace,
                "retrieval",
                "V3 Search / Auto Retrieval + v3.5-search-candidate-v1",
                request.search_request().model_dump(mode="json"),
                lambda: self.evidence_search.search_library(request.search_request()),
            )
            response["search_candidate_set"] = asdict(search_set)
            response["search_candidate_set_summary"] = {
                "contract_version": search_set.contract_version,
                "search_trace_id": search_set.search_trace_id,
                "raw_unit_candidate_count": len(search_set.raw_unit_candidates),
                "video_candidate_count": len(search_set.video_candidates),
                "reason_codes": list(search_set.reason_codes),
            }
            search_id = stable_id("search_candidate_set_", asdict(search_set))

            candidate_set = self._stage(
                trace,
                "candidate_builder",
                FINAL_CANDIDATE_BUILDER_VERSION,
                {"search_candidate_set_id": search_id},
                lambda: resolve_from_search_candidates(
                    request.query,
                    asdict(search_set),
                    self._raw_source,
                    self.builder_config,
                    query_id=request_id,
                    search_candidate_set_id=search_id,
                    execution_manifest_identity=STAGE5_PIPELINE_VERSION,
                ),
            )
            candidate_set_id = stable_id(
                "evidence_candidate_set_", candidate_set.as_dict()
            )
            response["evidence_candidate_set_summary"] = {
                "evidence_candidate_set_id": candidate_set_id,
                "candidate_count": len(candidate_set.candidates),
                "normalization_status": candidate_set.normalization_status,
                "failure_category": candidate_set.failure_category,
            }

            bundle = self._stage(
                trace,
                "fine_selector",
                DETERMINISTIC_SELECTOR_VERSION,
                {"evidence_candidate_set_id": candidate_set_id},
                lambda: select_deterministic_bundle(
                    request.query, candidate_set, self.selector_config
                ),
            )
            if bundle is not None:
                validate_bundle(bundle, candidate_set)
            reason = candidate_set.failure_category
            if reason is None and bundle is None:
                reason = "selector_failed"
            sufficiency_request, resolution = self._sufficiency_request(
                request,
                request_id=request_id,
                trace_id=trace_id,
                search_candidate_set_id=search_id,
                candidate_set_id=candidate_set_id,
                candidate_set=candidate_set,
                bundle=bundle,
                reason=reason,
            )
            gate = self._stage(
                trace,
                "mechanical_gate",
                "mechanical-gate-v1-r1",
                {
                    "request": sufficiency_request.model_dump(mode="json"),
                    "resolution": resolution.model_dump(mode="json"),
                },
                lambda: apply_mechanical_sufficiency_gate(
                    sufficiency_request, resolution, bundle, self.gate_policy
                ),
            )
            response["evidence_bundle"] = (
                self._present_bundle(bundle, candidate_set, search_set)
                if bundle is not None
                else None
            )
            response["mechanical_gate_result"] = {
                "status": gate.gate_outcome,
                "reason_codes": list(gate.validation_errors)
                or ([gate.operational_reason_code] if gate.operational_reason_code else []),
                "operational_reason_code": gate.operational_reason_code,
                "semantic_judge_required": gate.semantic_judge_required,
                "terminal_status": gate.terminal_status,
            }
            decision = self._route_semantic(
                trace,
                request=request,
                sufficiency_request=sufficiency_request,
                gate=gate,
                bundle=bundle,
            )
            response["sufficiency_decision"] = (
                decision.model_dump(mode="json") if decision else None
            )
            response["semantic_sufficiency"] = {
                "status": decision.status if decision else None,
                "bypassed": decision is None,
                "bypass_reason": (
                    gate.operational_reason_code
                    if decision is None
                    else None
                ),
            }
            response["pipeline_status"] = "completed"
            trace["final_pipeline_status"] = "completed"
        except Stage5IntegrationError as exc:
            response["pipeline_status"] = "failed"
            response["errors"].append(exc.as_dict())
            trace["final_pipeline_status"] = "failed"
        except EvidenceContractError as exc:
            response["pipeline_status"] = "failed"
            response["errors"].append(
                {
                    "type": "retrieval_or_resolution_error",
                    "stage": "evidence_resolution",
                    "code": exc.code,
                    "message": str(exc)[:500],
                }
            )
            trace["final_pipeline_status"] = "failed"
        except Exception as exc:
            stages = trace.get("stages", [])
            last_stage = stages[-1] if isinstance(stages, list) and stages else {}
            response["pipeline_status"] = "failed"
            response["errors"].append(
                {
                    "type": last_stage.get(
                        "error_type", "internal_integration_error"
                    ),
                    "stage": last_stage.get("stage_name", "integration"),
                    "message": f"{type(exc).__name__}: {exc}"[:500],
                }
            )
            trace["final_pipeline_status"] = "failed"
        trace["completed_at"] = _utc_now()
        trace["total_latency_ms"] = _elapsed_ms(started)
        response["total_latency_ms"] = trace["total_latency_ms"]
        response["stage_latencies"] = {
            str(stage["stage_name"]): stage["latency_ms"]
            for stage in trace["stages"]  # type: ignore[union-attr]
        }
        response["trace"] = trace
        self._persist_trace(trace)
        return response

    def get_trace(self, trace_id: str) -> dict[str, object] | None:
        if not trace_id.startswith("stage5_trace_") or any(
            value not in "0123456789abcdef" for value in trace_id.removeprefix("stage5_trace_")
        ):
            return None
        path = self.trace_dir / f"{trace_id}.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _route_semantic(
        self,
        trace: dict[str, object],
        *,
        request: Stage5PipelineRequest,
        sufficiency_request: SufficiencyRequest,
        gate: MechanicalGateDecision,
        bundle: EvidenceBundle | None,
    ) -> SufficiencyDecision | None:
        if gate.gate_outcome != "judge_eligible":
            self._stage(
                trace,
                "semantic_judge_or_bypass",
                SEMANTIC_POLICY_VERSION,
                {"gate_outcome": gate.gate_outcome},
                lambda: {
                    "bypassed": True,
                    "bypass_reason": gate.operational_reason_code,
                },
            )
            return None
        if bundle is None:
            raise Stage5IntegrationError(
                "judge-eligible gate has no EvidenceBundle",
                error_type="internal_integration_error",
                stage="semantic_judge",
            )
        runtime_request = project_runtime_request(
            sufficiency_request,
            gate,
            bundle,
            query_language=request.query_language,
        )
        decision, judge_trace = self._stage(
            trace,
            "semantic_judge_or_bypass",
            SEMANTIC_POLICY_VERSION,
            runtime_request.model_dump(mode="json"),
            lambda: self.judge.judge(runtime_request, bundle),
            output_value=lambda value: value[0].model_dump(mode="json"),
            extra=lambda value: {
                **value[1],
                "evidence_ids_used": list(value[0].evidence_ids_used),
            },
        )
        return decision

    def _sufficiency_request(
        self,
        request: Stage5PipelineRequest,
        *,
        request_id: str,
        trace_id: str,
        search_candidate_set_id: str,
        candidate_set_id: str,
        candidate_set: EvidenceCandidateSet,
        bundle: EvidenceBundle | None,
        reason: str | None,
    ) -> tuple[SufficiencyRequest, EvidenceResolutionState]:
        status = "resolved" if reason is None and bundle is not None else "failed"
        source_states = tuple(
            sorted({candidate.normalization_status for candidate in candidate_set.candidates})
        )
        languages = tuple(
            sorted({candidate.source_language for candidate in candidate_set.candidates})
        )
        base = {
            "query_id": request_id,
            "original_query": request.query,
            "evaluation_track": "frozen_v3_end_to_end",
            "end_to_end_claim_eligible": True,
            "search_candidate_set_id": search_candidate_set_id,
            "evidence_candidate_set_id": candidate_set_id,
            "evidence_bundle_id": bundle.bundle_id if bundle else None,
            "evidence_resolution_status": status,
            "failure_attribution": reason,
            "candidate_builder_version": FINAL_CANDIDATE_BUILDER_VERSION,
            "selector_version": DETERMINISTIC_SELECTOR_VERSION,
            "source_states": source_states,
            "source_languages": languages,
            "trace_id": trace_id,
        }
        formal_request = SufficiencyRequest(
            request_id=stable_id(
                "sufficiency_request_",
                {"contract": SUFFICIENCY_REQUEST_CONTRACT_VERSION, **base},
            ),
            **base,
        )
        resolution = EvidenceResolutionState(
            status=status,
            operational_reason_code=reason,
            search_candidate_set_id=search_candidate_set_id,
            evidence_candidate_set_id=candidate_set_id,
            evidence_bundle_id=bundle.bundle_id if bundle else None,
            available_evidence_candidate_ids=tuple(
                candidate.candidate_id for candidate in candidate_set.candidates
            ),
            evidence_ids_raw_derived=bool(candidate_set.candidates),
            source_integrity_valid=(
                candidate_set.normalization_status == "valid"
                and not candidate_set.validation_errors
            ),
            validation_errors=candidate_set.validation_errors,
        )
        return formal_request, resolution

    def _raw_source(self, video_id: int):
        row = self.db.get_video(video_id)
        if row is None or not row.get("raw_subtitle_path"):
            raise EvidenceContractError(
                "authoritative raw subtitle is unavailable",
                code="raw_source_unavailable",
            )
        try:
            path = self.artifacts.managed_file(str(row["raw_subtitle_path"]))
        except (ValueError, FileNotFoundError) as exc:
            raise EvidenceContractError(str(exc), code="raw_source_unavailable") from exc
        return load_source_artifact(
            SourceArtifactReference(
                platform=str(row["platform"]),
                source_id=str(row["source_id"]),
                part=int(row["part"]),
                source_type=str(row.get("subtitle_source") or "unknown"),
                source_language=str(row.get("subtitle_language") or "unknown"),
                artifact_path=str(path),
            )
        )

    def _stage(
        self,
        trace: dict[str, object],
        stage_name: str,
        component_version: str,
        input_value: object,
        function: Callable[[], Any],
        *,
        output_value: Callable[[Any], object] | None = None,
        extra: Callable[[Any], dict[str, object]] | None = None,
    ) -> Any:
        started = time.perf_counter()
        started_at = _utc_now()
        stage: dict[str, object] = {
            "stage_name": stage_name,
            "component_version": component_version,
            "input_hash": _hash(input_value),
            "output_hash": None,
            "status": "processing",
            "started_at": started_at,
            "completed_at": None,
            "latency_ms": None,
            "retry_count": 0,
            "error_type": None,
            "parent_trace_id": trace["trace_id"],
        }
        trace["stages"].append(stage)  # type: ignore[union-attr]
        try:
            result = function()
            serialized = output_value(result) if output_value else _serializable(result)
            stage["output_hash"] = _hash(serialized)
            stage["status"] = "completed"
            if extra:
                stage.update(extra(result))
            return result
        except Stage5IntegrationError as exc:
            stage["status"] = "failed"
            stage["retry_count"] = exc.retry_count
            stage["error_type"] = exc.error_type
            raise
        except Exception as exc:
            stage["status"] = "failed"
            stage["error_type"] = _stage_error_type(stage_name, exc)
            raise
        finally:
            stage["completed_at"] = _utc_now()
            stage["latency_ms"] = _elapsed_ms(started)

    def _base_response(
        self,
        request: Stage5PipelineRequest,
        request_id: str,
        trace_id: str,
    ) -> dict[str, object]:
        return {
            "pipeline_contract_version": STAGE5_PIPELINE_VERSION,
            "request_id": request_id,
            "trace_id": trace_id,
            "query": request.query,
            "pipeline_status": "processing",
            "total_latency_ms": None,
            "search_candidate_set_summary": None,
            "search_candidate_set": None,
            "evidence_candidate_set_summary": None,
            "evidence_bundle": None,
            "mechanical_gate_result": None,
            "semantic_sufficiency": None,
            "sufficiency_decision": None,
            "component_versions": {
                "retrieval": "V3 Search / Auto Retrieval",
                "candidate_builder": FINAL_CANDIDATE_BUILDER_VERSION,
                "fine_selector": DETERMINISTIC_SELECTOR_VERSION,
                "mechanical_gate": "mechanical-gate-v1-r1",
                "mechanical_gate_contract": MECHANICAL_GATE_CONTRACT_VERSION,
                "semantic_judge_provider": SEMANTIC_JUDGE_PROVIDER,
                "semantic_judge_model": SEMANTIC_JUDGE_MODEL,
                "semantic_judge_policy": SEMANTIC_POLICY_VERSION,
                "semantic_judge_prompt": SEMANTIC_PROMPT_VERSION,
                "semantic_judge_contract": SEMANTIC_JUDGE_CONTRACT_VERSION,
            },
            "stage_latencies": {},
            "warnings": [
                "本版本只判断现有证据是否充分，不生成最终答案。",
                "端到端结果仍可能受 Retrieval 与 Evidence Resolution 限制。",
            ],
            "errors": [],
            "final_answer_generated": False,
        }

    @staticmethod
    def _present_bundle(
        bundle: EvidenceBundle,
        candidate_set: EvidenceCandidateSet,
        search_set: SearchCandidateSet,
    ) -> dict[str, object]:
        by_candidate = {
            candidate.candidate_id: candidate for candidate in candidate_set.candidates
        }
        titles = {
            candidate.video_id: candidate.title
            for candidate in search_set.video_candidates
        }
        evidence = []
        for candidate_id in bundle.candidate_ids:
            candidate = by_candidate[candidate_id]
            evidence.append(
                {
                    "evidence_id": candidate.candidate_id,
                    "video_id": candidate.video_id,
                    "title_or_available_video_metadata": titles.get(candidate.video_id),
                    "segment_ids": list(candidate.segment_ids),
                    "start_time": candidate.start_time,
                    "end_time": candidate.end_time,
                    "quote_text": candidate.source_text,
                    "source_language": candidate.source_language,
                    "source_type": candidate.source_type,
                    "selector_method": bundle.selection_method,
                    "timeline_run_id": candidate.timeline_run_id,
                    "source_artifact_id": candidate.source_artifact_id,
                    "source_version": candidate.source_version,
                }
            )
        return {**bundle.as_dict(), "evidence": evidence}

    def _persist_trace(self, trace: dict[str, object]) -> None:
        path = self.trace_dir / f"{trace['trace_id']}.json"
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(trace, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)


def _stage_error_type(stage_name: str, error: Exception) -> str:
    if stage_name == "retrieval":
        return "retrieval_or_resolution_error"
    if stage_name in {"candidate_builder", "fine_selector"}:
        return "retrieval_or_resolution_error"
    if stage_name == "mechanical_gate":
        return "mechanical_invalid"
    if isinstance(error, (json.JSONDecodeError, ValueError)):
        return "structured_output_error"
    return "internal_integration_error"


def _serializable(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool, list, tuple, dict)):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")  # type: ignore[union-attr]
    if hasattr(value, "as_dict"):
        return value.as_dict()  # type: ignore[union-attr]
    try:
        return asdict(value)  # type: ignore[arg-type]
    except TypeError:
        return repr(value)


def _hash(value: object) -> str:
    if isinstance(value, str):
        payload = value.encode("utf-8")
    else:
        payload = canonical_bytes(_serializable(value))
    return sha256(payload).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
