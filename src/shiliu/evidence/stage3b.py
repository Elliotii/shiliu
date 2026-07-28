from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import time
from typing import Any, Literal, Protocol, Sequence

from pydantic import BaseModel, ConfigDict, ValidationError

from shiliu.domain import PipelineError
from shiliu.evidence.source import canonical_json
from shiliu.evidence.stage3a import (
    EVIDENCE_BUNDLE_CONTRACT_VERSION,
    EvidenceBundle,
    EvidenceCandidate,
    EvidenceCandidateSet,
    interval_union_duration,
    validate_bundle,
)
from shiliu.llm import CompletionResponse


STRUCTURED_SELECTOR_CONTRACT_VERSION = "v3.5-structured-fine-selector-v1"
STRUCTURED_SELECTOR_PROMPT_VERSION = "v3.5-structured-fine-selector-prompt-v1"
STRUCTURED_SELECTOR_ERROR_CODES = frozenset({
    "provider_failure", "provider_timeout", "invalid_json",
    "schema_validation_failure", "unknown_candidate_id", "duplicate_candidate_id",
    "candidate_count_exceeded", "invalid_abstain_contract", "repair_attempt_exhausted",
})


class StructuredSelectorError(RuntimeError):
    def __init__(self, message: str, *, code: str, metrics: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.metrics = metrics or {}


class CandidateRole(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    role: Literal["primary", "complementary", "context"]


class StructuredSelectorOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["v3.5-structured-fine-selector-v1"]
    action: Literal["select", "abstain"]
    selected_candidate_ids: list[str]
    candidate_roles: list[CandidateRole]
    abstain_reason: Literal[
        "no_relevant_candidate", "insufficient_candidate_coverage",
        "conflicting_or_ambiguous", "provider_unable_to_decide",
    ] | None


@dataclass(frozen=True)
class StructuredSelectorConfig:
    config_id: str = "stage3b-structured-selector-full-v1"
    max_candidates: int = 32
    max_candidate_characters: int = 6000
    max_selected_candidates: int = 6
    timeout_seconds: float = 120.0
    max_output_tokens: int = 2048
    max_repair_attempts: int = 1
    prompt_version: str = STRUCTURED_SELECTOR_PROMPT_VERSION
    schema_version: str = STRUCTURED_SELECTOR_CONTRACT_VERSION


class StructuredProvider(Protocol):
    name: str
    model: str

    def complete_raw(self, prompt: str, *, max_tokens: int | None = None) -> CompletionResponse: ...


@dataclass(frozen=True)
class StructuredSelectionResult:
    output: StructuredSelectorOutput
    bundle: EvidenceBundle | None
    request_hash: str
    candidate_set_hash: str
    response_hash: str
    prompt: str
    metrics: dict[str, Any]


def _hash(value: object) -> str:
    return sha256(canonical_json(value)).hexdigest()


def serialize_candidates(candidates: Sequence[EvidenceCandidate], config: StructuredSelectorConfig) -> list[dict[str, Any]]:
    if len(candidates) > config.max_candidates:
        raise StructuredSelectorError("CandidateSet exceeds configured input count", code="candidate_count_exceeded")
    if sum(value.character_count for value in candidates) > config.max_candidate_characters:
        raise StructuredSelectorError("CandidateSet exceeds configured character budget", code="candidate_count_exceeded")
    return [
        {
            "candidate_id": value.candidate_id,
            "rank": rank,
            "start_time": value.start_time,
            "end_time": value.end_time,
            "source_language": value.source_language,
            "source_type": value.source_type,
            "candidate_generation_method": list(value.candidate_methods),
            "parent_rank": value.parent_rank,
            "text": value.source_text,
        }
        for rank, value in enumerate(candidates, start=1)
    ]


def build_structured_selector_prompt(
    query: str, candidates: Sequence[EvidenceCandidate], config: StructuredSelectorConfig,
    *, repair_error: str | None = None,
) -> str:
    payload = {
        "original_query": query,
        "evidence_candidate_contract_version": "v3.5-evidence-candidate-v1",
        "candidates": serialize_candidates(candidates, config),
    }
    repair = "" if repair_error is None else (
        "\nSCHEMA REPAIR ONLY: Your prior response was invalid: " + repair_error
        + ". Use the identical query and CandidateSet below; return only a corrected JSON object.\n"
    )
    return f"""Structured selector contract: {config.schema_version}
Prompt version: {config.prompt_version}

Select one or more existing Candidate IDs that jointly provide the most relevant, complete,
and non-duplicative raw subtitle evidence for Original Query, or abstain when the supplied
candidates do not contain sufficiently relevant evidence.

You must not answer or summarize the query. Do not create candidates, quotes, text, timestamps,
labels, or fields. Do not infer evidence outside the supplied CandidateSet. Return JSON only.

Exact output fields:
schema_version, action, selected_candidate_ids, candidate_roles, abstain_reason.
action is select or abstain. Roles are primary, complementary, or context.
For select: IDs are non-empty, unique, drawn only from the CandidateSet, at most
{config.max_selected_candidates}; abstain_reason is null. Every role references a selected ID.
For abstain: IDs and roles are empty, and abstain_reason is one of no_relevant_candidate,
insufficient_candidate_coverage, conflicting_or_ambiguous, provider_unable_to_decide.
No additional fields are allowed.{repair}
INPUT_JSON:
{json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))}
"""


def _parse_and_validate(
    content: str, candidates_by_id: dict[str, EvidenceCandidate], config: StructuredSelectorConfig,
) -> StructuredSelectorOutput:
    try:
        payload = json.loads(content)
    except (json.JSONDecodeError, TypeError) as exc:
        raise StructuredSelectorError(str(exc), code="invalid_json") from exc
    try:
        value = StructuredSelectorOutput.model_validate(payload)
    except ValidationError as exc:
        raise StructuredSelectorError(str(exc), code="schema_validation_failure") from exc
    selected = value.selected_candidate_ids
    if len(selected) != len(set(selected)):
        raise StructuredSelectorError("selected Candidate IDs are duplicated", code="duplicate_candidate_id")
    if any(candidate_id not in candidates_by_id for candidate_id in selected):
        raise StructuredSelectorError("selection contains an unknown Candidate ID", code="unknown_candidate_id")
    if len(selected) > config.max_selected_candidates:
        raise StructuredSelectorError("selected Candidate count exceeds configuration", code="candidate_count_exceeded")
    role_ids = [role.candidate_id for role in value.candidate_roles]
    if len(role_ids) != len(set(role_ids)) or any(candidate_id not in selected for candidate_id in role_ids):
        raise StructuredSelectorError("candidate_roles must uniquely reference selected Candidates", code="schema_validation_failure")
    if value.action == "select":
        if not selected or value.abstain_reason is not None:
            raise StructuredSelectorError("select requires IDs and a null abstain_reason", code="invalid_abstain_contract")
        if len({candidates_by_id[value].video_id for value in selected}) != 1:
            raise StructuredSelectorError("selected Candidates must belong to one video", code="schema_validation_failure")
    elif selected or value.candidate_roles or value.abstain_reason is None:
        raise StructuredSelectorError("abstain requires empty IDs/roles and a reason", code="invalid_abstain_contract")
    return value


def reconstruct_structured_bundle(
    output: StructuredSelectorOutput, candidate_set: EvidenceCandidateSet,
) -> EvidenceBundle | None:
    if output.action == "abstain":
        return None
    by_id = {value.candidate_id: value for value in candidate_set.candidates}
    selected = [by_id[value] for value in output.selected_candidate_ids]
    if len({value.video_id for value in selected}) != 1:
        raise StructuredSelectorError("selected Candidates cross videos", code="schema_validation_failure")
    selected.sort(key=lambda value: (value.start_time, value.end_time, value.candidate_id))
    candidate_ids = tuple(value.candidate_id for value in selected)
    bundle_id = "bundle_" + _hash({
        "contract_version": EVIDENCE_BUNDLE_CONTRACT_VERSION,
        "query_id": candidate_set.query_id,
        "video_id": selected[0].video_id,
        "candidate_ids": list(candidate_ids),
        "selector": STRUCTURED_SELECTOR_CONTRACT_VERSION,
    })
    bundle = EvidenceBundle(
        bundle_id=bundle_id,
        query_id=candidate_set.query_id,
        video_id=selected[0].video_id,
        source_artifact_ids=tuple(sorted({value.source_artifact_id for value in selected})),
        source_versions=tuple(sorted({value.source_version for value in selected})),
        timeline_run_ids=tuple(sorted({value.timeline_run_id for value in selected})),
        candidate_ids=candidate_ids,
        normalized_spans=tuple({
            "candidate_id": value.candidate_id,
            "timeline_run_id": value.timeline_run_id,
            "start_time": value.start_time,
            "end_time": value.end_time,
            "segment_ids": list(value.segment_ids),
        } for value in selected),
        union_duration=interval_union_duration((value.start_time, value.end_time) for value in selected),
        source_texts=tuple(value.source_text for value in selected),
        selection_method=STRUCTURED_SELECTOR_CONTRACT_VERSION,
        score=0.0,
        score_breakdown={"provider_selected_candidate_count": float(len(selected))},
        evaluation_track=candidate_set.evaluation_track,
        end_to_end_claim_eligible=candidate_set.end_to_end_claim_eligible,
        trace_id="trace_" + _hash({"bundle_id": bundle_id, "selected_candidate_ids": list(candidate_ids)}),
        normalization_status="valid",
        validation_errors=(),
    )
    validate_bundle(bundle, candidate_set)
    return bundle


def select_structured_evidence_bundle(
    query: str, candidates: EvidenceCandidateSet, provider: StructuredProvider,
    config: StructuredSelectorConfig | None = None,
) -> StructuredSelectionResult:
    config = config or StructuredSelectorConfig()
    serialized = serialize_candidates(candidates.candidates, config)
    candidate_set_hash = _hash(serialized)
    candidates_by_id = {value.candidate_id: value for value in candidates.candidates}
    attempts: list[dict[str, Any]] = []
    last_error: StructuredSelectorError | None = None
    response: CompletionResponse | None = None
    prompt = ""
    for attempt_index in range(config.max_repair_attempts + 1):
        prompt = build_structured_selector_prompt(
            query, candidates.candidates, config,
            repair_error=(f"{last_error.code}: {last_error}" if last_error else None),
        )
        started = time.monotonic()
        try:
            response = provider.complete_raw(prompt, max_tokens=config.max_output_tokens)
        except TimeoutError as exc:
            raise StructuredSelectorError(str(exc), code="provider_timeout") from exc
        except PipelineError as exc:
            code = "provider_timeout" if "timeout" in exc.code or "network" in exc.code else "provider_failure"
            raise StructuredSelectorError(str(exc), code=code) from exc
        except Exception as exc:
            raise StructuredSelectorError(str(exc), code="provider_failure") from exc
        latency = time.monotonic() - started
        try:
            output = _parse_and_validate(response.content, candidates_by_id, config)
        except StructuredSelectorError as exc:
            attempts.append({"attempt": attempt_index + 1, "latency_seconds": latency, "validation": exc.code})
            last_error = exc
            if attempt_index < config.max_repair_attempts:
                continue
            raise StructuredSelectorError(
                f"structured output remained invalid after one repair: {exc.code}",
                code="repair_attempt_exhausted",
                metrics={"attempts": attempts},
            ) from exc
        attempts.append({"attempt": attempt_index + 1, "latency_seconds": latency, "validation": "valid"})
        bundle = reconstruct_structured_bundle(output, candidates)
        usage = response.usage if response.usage is not None else "unavailable"
        metrics = {
            "model_identity": provider.model,
            "provider_abstraction": provider.name,
            "prompt_version": config.prompt_version,
            "schema_version": config.schema_version,
            "attempt_count": len(attempts),
            "repair_used": len(attempts) > 1,
            "latency_seconds": sum(float(value["latency_seconds"]) for value in attempts),
            "usage": usage,
            "cost": "unavailable",
            "attempts": attempts,
        }
        return StructuredSelectionResult(
            output=output,
            bundle=bundle,
            request_hash=_hash({"prompt": prompt, "config": asdict(config), "model": provider.model}),
            candidate_set_hash=candidate_set_hash,
            response_hash=_hash({"content": response.content}),
            prompt=prompt,
            metrics=metrics,
        )
    raise AssertionError("unreachable")
