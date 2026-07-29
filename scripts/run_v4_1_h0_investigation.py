from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import sys
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Any, Callable, Iterable, Iterator
from unittest.mock import patch

from shiliu.app import Application
from shiliu.ask.answer import (
    GroundedAnswerResult,
    GroundedAnswerService,
    _answer_messages,
)
from shiliu.ask.context import (
    ContextBuildResult,
    TranscriptContextBuilder,
    _fit_span,
    _merge_spans,
    _same_lineage,
    _segment_relation,
    fuse_evidence,
)
from shiliu.ask.contracts import (
    AskRequest,
    GroundedAnswerDraft,
    TranscriptEvidenceSpan,
)
from shiliu.ask.deep.budget import DeepSearchBudget
from shiliu.ask.deep.contracts import AgentDecision, DeepSearchState
from shiliu.ask.deep.decision import _decision_messages
from shiliu.ask.deep.policy import DEEP_POLICY_INSTRUCTIONS
from shiliu.ask.evidence import TranscriptEvidenceMaterializer
from shiliu.config import AppPaths, load_api_key, load_config
from shiliu.evidence.search import EvidenceSearchService
from shiliu.llm import OpenAICompatibleProvider
from shiliu.retrieval.product_search import ProductSearchRequest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPOSITORY_ROOT / "eval" / "v4_goal3_cases.json"
REAL_USAGE_PATHS = (
    REPOSITORY_ROOT / "eval" / "v4_goal3_results.json",
    REPOSITORY_ROOT / "eval" / "v4_goal3_repair_results.json",
)
LIVE_AUTHORIZATION_PHRASE = "USER_AUTHORIZED_H0_LIVE_PROVIDER_REPLAY"
E2E_AUTHORIZATION_PHRASE = "USER_AUTHORIZED_H0_END_TO_END"
ESTIMATION_METHOD = "ceil(utf8-independent Unicode character count / 4)"
CONSECUTIVE_PROVIDER_FAILURE_LIMIT = 3
QUALITY_VALUES = {"pass", "partial", "fail"}
CHECKPOINT_VERSION = "h0-fixed-replay-checkpoint-v1"
DEFAULT_CHECKPOINT_PATH = (
    REPOSITORY_ROOT / ".h0" / "v4_1_fixed_replay_checkpoint.json"
)
TTY_PREFLIGHT_PREFIX = "H0-REVIEW-READY"
MAX_LOGICAL_PROVIDER_INVOCATIONS = 48
MAX_TRANSPORT_HTTP_ATTEMPTS = 96
MAX_LOGICAL_INVOCATIONS_PER_TRIAL = 2
MAX_TRANSPORT_ATTEMPTS_PER_TRIAL = 4
_TTY_PREFLIGHT_PROOFS: set[tuple[int, str]] = set()


SCRIPTED_REWRITES: dict[str, tuple[str, str]] = {
    "direct_fact_mcp": (
        "MCP 模型上下文协议 外部工具",
        "Model Context Protocol 客户端 服务端 工具",
    ),
    "single_topic_context_compression": (
        "上下文压缩 自动压缩 性能",
        "context compression 上下文窗口",
    ),
    "contextual_tool_failure": (
        "工具调用失败 调整 重试 继续任务",
        "tool failure 观察 重新规划",
    ),
    "cross_video_context_management": (
        "上下文管理 上下文工程 比较",
        "context management context engineering",
    ),
    "partial_universal_claim": (
        "自动上下文压缩 性能 Agent 任务",
        "上下文压缩 反例 性能下降",
    ),
    "no_evidence_quantum_protocol": (
        "Shiliu-X9 量子检索协议",
        "量子检索 protocol X9",
    ),
}

FIXED_REQUEST_CASES = (
    "no_evidence_quantum_protocol",
    "single_topic_context_compression",
    "cross_video_context_management",
    "partial_universal_claim",
)


@dataclass(frozen=True)
class ProviderVariant:
    name: str
    thinking: bool
    reasoning_effort: str | None

    def public_configuration(self) -> dict[str, object]:
        return {
            "configuration_id": self.name,
            "thinking": self.thinking,
            "reasoning_effort": self.reasoning_effort,
            "temperature": 0 if self.thinking is False else "provider_default",
        }


BASELINE = ProviderVariant("baseline", True, "high")
THINKING_OFF = ProviderVariant("thinking_off", False, None)
LIVE_VARIANTS = (BASELINE, THINKING_OFF)


@dataclass(frozen=True)
class FastAudit:
    case_id: str
    raw_materialized_span_count: int
    candidate_span_count: int
    selected_span_count: int
    candidate_video_count: int
    selected_video_count: int
    candidate_per_video_span_count: dict[str, int]
    selected_per_video_span_count: dict[str, int]
    overlapping_span_count: int
    exact_citation_duplicate_count: int
    duplicate_content_count: int
    dropped_span_count: int
    builder_dropped_event_count: int
    builder_drop_event_overcount: int
    merged_candidate_span_count: int
    per_span_trimmed_candidate_count: int
    selection_outcomes: dict[str, int]
    dropped_video_count: int
    candidate_chars: int
    selected_chars: int
    dropped_chars: int
    dropped_chars_precision: str
    selected_query_sources: list[dict[str, object]]
    context_truncated: bool
    per_span_fit_count: int
    max_span_limit_reached: bool
    total_character_budget_reached: bool
    rewrite_duplicate_recall_count: int
    stale_count: int
    retrieval_error_count: int
    model_context_sha256: str
    citation_allowlist_sha256: str
    selected_span_identity_sha256: str


@dataclass(frozen=True)
class FixedRequest:
    case_id: str
    query: str
    context: ContextBuildResult
    messages: list[dict[str, str]]
    request_hash: str
    message_chars: int
    context_chars: int
    citation_allowlist_count: int
    source_version_hashes: tuple[str, ...]

    def bounded_summary(self) -> dict[str, object]:
        return {
            "request_id": self.case_id,
            "request_hash": self.request_hash,
            "message_chars": self.message_chars,
            "context_chars": self.context_chars,
            "citation_allowlist_count": self.citation_allowlist_count,
            "source_version_hashes": list(self.source_version_hashes),
        }


@dataclass(frozen=True)
class TrialRecord:
    """Private trial payload plus the bounded public measurement."""

    trial_id: str
    request: FixedRequest
    configuration: ProviderVariant
    measurement: dict[str, object]
    draft: GroundedAnswerDraft | None
    citation_ids: tuple[str, ...]

    @property
    def provider_failed(self) -> bool:
        return (
            self.draft is None
            and self.measurement.get("provider_error_code") is not None
        )

    @property
    def behavior_hash(self) -> str:
        return stable_hash(
            {
                "draft": (
                    self.draft.model_dump(mode="json")
                    if self.draft is not None
                    else None
                ),
                "provider_error_code": self.measurement.get(
                    "provider_error_code"
                ),
                "validation_error_codes": self.measurement.get(
                    "validation_error_codes"
                ),
            }
        )

    def public_measurement(self) -> dict[str, object]:
        return {
            **self.measurement,
            "trial_id": self.trial_id,
            "configuration": self.configuration.public_configuration(),
            "final_draft_hash": (
                stable_hash(self.draft.model_dump(mode="json"))
                if self.draft is not None
                else None
            ),
            "final_citation_ids": list(self.citation_ids),
        }


@dataclass(frozen=True)
class CampaignResult:
    trials: tuple[TrialRecord, ...]
    expected_trial_count: int
    consecutive_failure_limit: int
    stopped_early: bool
    stop_reason: str | None

    @property
    def matrix_complete(self) -> bool:
        return (
            not self.stopped_early
            and len(self.trials) == self.expected_trial_count
        )

    def bounded_summary(self) -> dict[str, object]:
        return {
            "expected_trial_count": self.expected_trial_count,
            "completed_trial_count": len(self.trials),
            "matrix_complete": self.matrix_complete,
            "stopped_early": self.stopped_early,
            "stop_reason": self.stop_reason,
            "consecutive_provider_failure_limit": (
                self.consecutive_failure_limit
            ),
            "completed_trial_ids": [
                value.trial_id for value in self.trials
            ],
        }


@dataclass(frozen=True)
class QualityReviewMaterial:
    """Never serialize: full current Evidence exists only for the reviewer."""

    trial_id: str
    query: str
    draft: GroundedAnswerDraft | None
    cited_ids: tuple[str, ...]
    current_full_evidence: tuple[TranscriptEvidenceSpan, ...]
    material_hash: str


@dataclass(frozen=True)
class QualityScores:
    supportedness: str
    usefulness: str
    coverage: str
    status_honesty: str
    reason_summary: str

    def __post_init__(self) -> None:
        for field_name in (
            "supportedness",
            "usefulness",
            "coverage",
            "status_honesty",
        ):
            if getattr(self, field_name) not in QUALITY_VALUES:
                raise ValueError(
                    f"{field_name} must be pass, partial, or fail"
                )
        if not self.reason_summary.strip():
            raise ValueError("quality review requires a reason summary")


QualityReviewer = Callable[[QualityReviewMaterial], QualityScores]


@dataclass(frozen=True)
class TTYPreflightProof:
    process_id: int
    verified_at_utc: str
    challenge_hash: str
    read_write_roundtrip: bool

    @property
    def valid_for_current_process(self) -> bool:
        return (
            self.process_id == os.getpid()
            and self.read_write_roundtrip
            and bool(self.challenge_hash)
            and (self.process_id, self.challenge_hash)
            in _TTY_PREFLIGHT_PROOFS
        )


class ReplayRecoveryBlocked(RuntimeError):
    """A prior crash may have consumed a Provider call or private Draft."""


@dataclass
class _Reply:
    output: AgentDecision
    usage: dict[str, int]
    finish_reason: str = "stop"
    response_id: str = "h0-capture"
    latency_ms: float = 0
    retry_count: int = 0


class CaptureDecisionProvider:
    """Script decisions while preserving every current agent_action message."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def generate_structured(
        self,
        *,
        role: str,
        messages: list[dict[str, str]],
        response_schema: type[AgentDecision],
        max_tokens: int,
        timeout_seconds: float | None = None,
    ) -> _Reply:
        if role != "agent_action":
            raise AssertionError(f"unexpected capture role: {role}")
        copied = [dict(value) for value in messages]
        payload = json.loads(copied[-1]["content"])
        call_index = len(self.calls) + 1
        decision = _scripted_decision(call_index, payload)
        self.calls.append(
            {
                "messages": copied,
                "max_tokens": max_tokens,
                "timeout_seconds": timeout_seconds,
                "decision_kind": decision.action.kind,
            }
        )
        return _Reply(
            output=response_schema.model_validate(
                decision.model_dump(mode="json")
            ),
            usage={"prompt_tokens": 0, "completion_tokens": 0},
            response_id=f"h0-capture-{call_index}",
        )


class _FakeHTTPResponse:
    status_code = 200
    text = ""

    @staticmethod
    def json() -> dict[str, object]:
        return {
            "id": "h0-dry-run",
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "status": "insufficient",
                                "answer_blocks": [],
                                "limitations": ["bounded dry-run"],
                            }
                        )
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 2,
                "prompt_tokens_details": {"cached_tokens": 4},
                "completion_tokens_details": {"reasoning_tokens": 1},
            },
        }


class _CaptureHTTPClient:
    bodies: list[dict[str, object]] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def __enter__(self) -> "_CaptureHTTPClient":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def post(self, *args: object, **kwargs: object) -> _FakeHTTPResponse:
        body = kwargs.get("json")
        if not isinstance(body, dict):
            raise AssertionError("provider request body was not captured")
        self.bodies.append(dict(body))
        return _FakeHTTPResponse()


def _load_manifest() -> list[dict[str, Any]]:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return list(payload["cases"])


def _case_by_id(cases: Iterable[dict[str, Any]], case_id: str) -> dict[str, Any]:
    return next(value for value in cases if value["case_id"] == case_id)


def canonical_json(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def stable_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def normalized_text_hash(value: object) -> str:
    if isinstance(value, str):
        normalized: object = " ".join(value.split())
    else:
        normalized = value
    return stable_hash(normalized)


def estimated_tokens(characters: int) -> int:
    return math.ceil(max(0, characters) / 4)


def trial_schedule(
    variant_names: tuple[str, ...] = ("baseline", "thinking_off"),
    trials: int = 3,
) -> list[str]:
    if not variant_names or trials <= 0:
        raise ValueError("variants and trials must be non-empty")
    result: list[str] = []
    for round_index in range(trials):
        offset = round_index % len(variant_names)
        result.extend(
            (*variant_names[offset:], *variant_names[:offset])
        )
    return result


def extract_usage_metrics(
    usage_values: Iterable[dict[str, object]],
) -> dict[str, int | None]:
    values = list(usage_values)

    def sum_optional(extractor: Callable[[dict[str, object]], object]) -> int | None:
        found = [
            int(value)
            for item in values
            if isinstance((value := extractor(item)), (int, float))
        ]
        return sum(found) if found else None

    prompt_tokens = sum_optional(lambda item: item.get("prompt_tokens"))
    cache_hit = sum_optional(
        lambda item: (
            item.get("prompt_cache_hit_tokens")
            if item.get("prompt_cache_hit_tokens") is not None
            else (
                item.get("prompt_tokens_details") or {}
            ).get("cached_tokens")
            if isinstance(item.get("prompt_tokens_details"), dict)
            else None
        )
    )
    explicit_miss = sum_optional(
        lambda item: item.get("prompt_cache_miss_tokens")
    )
    cache_miss = explicit_miss
    if cache_miss is None and prompt_tokens is not None and cache_hit is not None:
        cache_miss = max(0, prompt_tokens - cache_hit)
    return {
        "prompt_tokens": prompt_tokens,
        "cache_hit_tokens": cache_hit,
        "cache_miss_tokens": cache_miss,
        "completion_tokens": sum_optional(
            lambda item: item.get("completion_tokens")
        ),
        "reasoning_tokens": sum_optional(
            lambda item: (
                item.get("completion_tokens_details") or {}
            ).get("reasoning_tokens")
            if isinstance(item.get("completion_tokens_details"), dict)
            else None
        ),
        "latency_ms": sum_optional(lambda item: item.get("latency_ms")),
    }


def _snapshot_database(source: Path, target: Path) -> None:
    # The product database uses DELETE journaling. immutable=1 is both read-only
    # and avoids creating lock/shm sidecars beside the user's database.
    source_connection = sqlite3.connect(source.as_uri() + "?immutable=1", uri=True)
    target_connection = sqlite3.connect(target)
    try:
        source_connection.backup(target_connection)
    finally:
        target_connection.close()
        source_connection.close()


@contextmanager
def snapshot_application() -> Iterator[Application]:
    default_paths = AppPaths.defaults()
    if not default_paths.database.is_file() or not default_paths.config.is_file():
        raise RuntimeError("Shiliu database or config is unavailable")
    config = load_config(default_paths)
    with TemporaryDirectory(prefix="shiliu-v4-1-h0-") as temp:
        root = Path(temp)
        state = root / "state"
        state.mkdir()
        database = state / "shiliu.db"
        _snapshot_database(default_paths.database, database)
        config_path = state / "config.toml"
        shutil.copy2(default_paths.config, config_path)
        content = Path(config.content_dir).expanduser()
        application = Application(
            AppPaths(
                state_dir=state,
                content_dir=content,
                database=database,
                config=config_path,
                logs_dir=state / "logs",
                videos_dir=content / "videos",
                sync_lock=state / "sync.lock",
            )
        )
        yield application


def _materialize_case(
    application: Application,
    case: dict[str, Any],
) -> tuple[list[object], list[str], list[str]]:
    evidence_search = EvidenceSearchService(
        db=application.db,
        product_search=application.product_search,
        authority_mode="live_current_exact_replay",
        runtime_corpus_identity=application.runtime_config.corpus_identity,
    )
    materializer = TranscriptEvidenceMaterializer(application.db)
    queries = (case["query"], *SCRIPTED_REWRITES[case["case_id"]])
    spans: list[object] = []
    stale: list[str] = []
    errors: list[str] = []
    for query_index, query in enumerate(queries):
        request = ProductSearchRequest(
            query=query,
            mode="auto",
            scope="transcript_chunk",
            result_limit=10,
            max_windows_per_video=2,
            filters=AskRequest(query=case["query"]).filters,
        )
        try:
            execution = evidence_search.execute_search(request)
            candidates = evidence_search.materialize_execution(execution)
            result = materializer.materialize(
                execution, candidates, query_index=query_index
            )
            spans.extend(result.spans)
            stale.extend(result.stale_reasons)
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}"[:200])
    return spans, stale, errors


def _overlap_pair_count(spans: list[object]) -> int:
    result = 0
    for index, left in enumerate(spans):
        left_ordinals = set(left.segment_ordinals)  # type: ignore[attr-defined]
        for right in spans[index + 1 :]:
            same_lineage = (
                left.source_artifact_id == right.source_artifact_id  # type: ignore[attr-defined]
                and left.source_version == right.source_version  # type: ignore[attr-defined]
                and left.timeline_run_id == right.timeline_run_id  # type: ignore[attr-defined]
            )
            if same_lineage and left_ordinals & set(right.segment_ordinals):  # type: ignore[attr-defined]
                result += 1
    return result


def _content_duplicate_count(spans: list[object]) -> int:
    identities: dict[str, set[str]] = {}
    for span in spans:
        key = " ".join(span.quote_text.split()).casefold()  # type: ignore[attr-defined]
        identities.setdefault(key, set()).add(span.citation_id)  # type: ignore[attr-defined]
    return sum(max(0, len(values) - 1) for values in identities.values())


def _shadow_context_selection(
    candidates: list[object],
    builder: TranscriptContextBuilder,
) -> tuple[tuple[object, ...], dict[str, int]]:
    """Mirror the current builder for diagnostics, never for model input."""

    selected: list[object] = []
    total = 0
    outcomes: Counter[str] = Counter()
    for source_span in candidates:
        final_outcome: str | None = None
        span = _fit_span(source_span, builder.per_span_character_budget)
        if span is None:
            outcomes["dropped_per_span_fit"] += 1
            continue
        if span.segment_ids != source_span.segment_ids:
            outcomes["trimmed_per_span_fit"] += 1
        merged = False
        for index, existing in enumerate(selected):
            if not _same_lineage(existing, span):
                continue
            relation = _segment_relation(existing, span)
            if relation == "separate":
                continue
            candidate = _merge_spans(existing, span)
            if len(candidate.quote_text) > builder.per_span_character_budget:
                if relation == "overlap":
                    outcomes[
                        "interaction_overlap_merge_too_large"
                    ] += 1
                    final_outcome = "dropped_overlap_merge_too_large"
                    merged = True
                continue
            delta = len(candidate.quote_text) - len(existing.quote_text)
            if total + delta > builder.total_character_budget:
                outcomes["interaction_merge_total_budget"] += 1
                final_outcome = "dropped_merge_total_budget"
                merged = True
                continue
            selected[index] = candidate
            total += delta
            final_outcome = f"merged_{relation}"
            merged = True
            break
        if merged:
            if final_outcome is None:
                raise AssertionError("merged candidate has no final outcome")
            outcomes[final_outcome] += 1
            continue
        if len(selected) >= builder.max_spans:
            outcomes["dropped_max_spans"] += 1
            continue
        if total + len(span.quote_text) > builder.total_character_budget:
            outcomes["dropped_total_character_budget"] += 1
            continue
        selected.append(span)
        total += len(span.quote_text)
        outcomes["selected_new"] += 1
    return tuple(selected), dict(sorted(outcomes.items()))


def audit_fast_case(
    application: Application, case: dict[str, Any]
) -> tuple[FastAudit, FixedRequest]:
    raw, stale, errors = _materialize_case(application, case)
    candidates = list(fuse_evidence(raw))  # type: ignore[arg-type]
    builder = TranscriptContextBuilder()
    context = builder.build(
        query=case["query"],
        normalized_intent=case["query"],
        spans=tuple(candidates),
    )
    shadow_selected, selection_outcomes = _shadow_context_selection(
        candidates, builder
    )
    if [
        value.model_dump(mode="json") for value in shadow_selected
    ] != [
        value.model_dump(mode="json") for value in context.spans
    ]:
        raise AssertionError(
            "runner-only context diagnostics diverged from current builder"
        )
    exact_dropped = sum(
        count
        for name, count in selection_outcomes.items()
        if name.startswith("dropped_")
    )
    merged_candidates = sum(
        count
        for name, count in selection_outcomes.items()
        if name.startswith("merged_")
    )
    if len(candidates) != len(context.spans) + exact_dropped + merged_candidates:
        raise AssertionError("selection outcome counts do not reconcile")
    raw_ids = [value.citation_id for value in raw]
    candidate_videos = Counter(str(value.video_id) for value in candidates)
    selected_videos = Counter(str(value.video_id) for value in context.spans)
    selected_video_ids = set(selected_videos)
    candidate_chars = sum(len(value.quote_text) for value in candidates)
    selected_chars = sum(len(value.quote_text) for value in context.spans)
    query_sources = {
        (
            int(source.get("query_index", -1)),
            stable_hash(str(source.get("query", ""))),
        )
        for span in context.spans
        for source in span.retrieval_provenance
        if source.get("query") is not None
    }
    selected_identity = [
        {
            "citation_id": value.citation_id,
            "segment_ids": list(value.segment_ids),
        }
        for value in context.spans
    ]
    audit = FastAudit(
        case_id=case["case_id"],
        raw_materialized_span_count=len(raw),
        candidate_span_count=len(candidates),
        selected_span_count=len(context.spans),
        candidate_video_count=len(candidate_videos),
        selected_video_count=len(selected_videos),
        candidate_per_video_span_count=dict(sorted(candidate_videos.items())),
        selected_per_video_span_count=dict(sorted(selected_videos.items())),
        overlapping_span_count=_overlap_pair_count(candidates),
        exact_citation_duplicate_count=len(raw_ids) - len(set(raw_ids)),
        duplicate_content_count=_content_duplicate_count(candidates),
        dropped_span_count=exact_dropped,
        builder_dropped_event_count=context.dropped_span_count,
        builder_drop_event_overcount=max(
            0, context.dropped_span_count - exact_dropped
        ),
        merged_candidate_span_count=merged_candidates,
        per_span_trimmed_candidate_count=selection_outcomes.get(
            "trimmed_per_span_fit", 0
        ),
        selection_outcomes=selection_outcomes,
        dropped_video_count=len(set(candidate_videos) - selected_video_ids),
        candidate_chars=candidate_chars,
        selected_chars=selected_chars,
        dropped_chars=max(0, candidate_chars - selected_chars),
        dropped_chars_precision=(
            "approximate_nonnegative_candidate_minus_selected;"
            "merge_overlap_and_fit_prevent_span-attribution_exactness"
        ),
        selected_query_sources=[
            {"query_index": index, "query_hash": query_hash}
            for index, query_hash in sorted(query_sources)
        ],
        context_truncated=context.truncated,
        per_span_fit_count=sum(
            len(value.quote_text) > builder.per_span_character_budget
            for value in candidates
        ),
        max_span_limit_reached=(
            len(candidates) > builder.max_spans
            and len(context.spans) >= builder.max_spans
        ),
        total_character_budget_reached=(
            candidate_chars > builder.total_character_budget
        ),
        rewrite_duplicate_recall_count=len(raw_ids) - len(set(raw_ids)),
        stale_count=len(stale),
        retrieval_error_count=len(errors),
        model_context_sha256=hashlib.sha256(
            context.model_context.encode("utf-8")
        ).hexdigest(),
        citation_allowlist_sha256=stable_hash(
            list(context.citation_allowlist)
        ),
        selected_span_identity_sha256=stable_hash(selected_identity),
    )
    messages = _answer_messages(query=case["query"], context=context)
    request_contract = {
        "role": "grounded_answer",
        "messages": messages,
        "response_schema": GroundedAnswerDraft.model_json_schema(),
        "max_tokens": 4096,
    }
    fixed = FixedRequest(
        case_id=case["case_id"],
        query=case["query"],
        context=context,
        messages=messages,
        request_hash=stable_hash(request_contract),
        message_chars=sum(len(value["content"]) for value in messages),
        context_chars=len(context.model_context),
        citation_allowlist_count=len(context.citation_allowlist),
        source_version_hashes=tuple(
            sorted(
                {
                    hashlib.sha256(value.source_version.encode("utf-8")).hexdigest()
                    for value in context.spans
                }
            )
        ),
    )
    return audit, fixed


def _scripted_decision(call_index: int, payload: dict[str, object]) -> AgentDecision:
    navigation = payload.get("navigation_documents")
    evidence = payload.get("transcript_evidence")
    if call_index == 1:
        action = {
            "kind": "search_navigation",
            "query": str(payload["question"]),
        }
    elif call_index == 2:
        video_ids = [
            int(value["video_id"])
            for value in navigation or []
            if isinstance(value, dict) and value.get("video_id")
        ][:4]
        action = {
            "kind": "search_transcripts",
            "query": str(payload["question"]),
            "video_ids": video_ids,
        }
    elif call_index == 3:
        anchors = payload.get("window_anchors")
        anchor_id = next(
            (
                value.get("anchor_segment_id")
                for value in anchors or []
                if isinstance(value, dict)
                and value.get("anchor_segment_id")
            ),
            None,
        )
        if anchor_id is None:
            return AgentDecision.model_validate(
                {"action": {"kind": "finish", "summary": "no window anchor"}}
            )
        action = {
            "kind": "read_transcript_window",
            "anchor_segment_id": str(anchor_id),
            "before": 2,
            "after": 2,
        }
    elif call_index == 4:
        action = {
            "kind": "search_navigation",
            "query": f"{payload['question']} 对比",
        }
    else:
        action = {"kind": "finish", "summary": "scripted audit complete"}
    return AgentDecision.model_validate(
        {
            "action": action,
            "open_questions": [str(payload["question"])],
            "resolved_questions": [],
        }
    )


def _json_field_fragment(key: str, value: object) -> str:
    return f"{json.dumps(key, ensure_ascii=False)}:{canonical_json(value)}"


def _breakdown_round(
    messages: list[dict[str, str]],
    previous_hashes: dict[str, str],
) -> dict[str, object]:
    system = messages[0]["content"]
    user = messages[1]["content"]
    payload = json.loads(user)
    schema_prefix = "\nRequired JSON Schema: "
    policy, separator, schema = system.partition(schema_prefix)
    if not separator:
        raise AssertionError("current decision system message layout changed")

    fragments = {
        key: _json_field_fragment(key, value)
        for key, value in payload.items()
    }
    evidence_fragment = fragments.get("transcript_evidence", "")
    evidence_quote_chars = sum(
        len(_json_field_fragment("quote", value.get("quote")))
        for value in payload.get("transcript_evidence", [])
        if isinstance(value, dict) and "quote" in value
    )
    navigation_chars = len(fragments.get("navigation_documents", ""))
    latest_chars = len(fragments.get("last_action", "")) + len(
        fragments.get("last_observation_summary", "")
    )
    allocated_user = {
        "original_query": len(fragments.get("question", "")),
        "current_goal": 0,
        "open_questions": len(fragments.get("open_questions", "")),
        "resolved_questions": len(fragments.get("resolved_questions", "")),
        "navigation_results": navigation_chars,
        "evidence_text": evidence_quote_chars,
        "evidence_metadata": max(0, len(evidence_fragment) - evidence_quote_chars),
        "latest_observation": latest_chars,
        "historical_observations": 0,
        "visited_video_ids": len(fragments.get("visited_video_ids", "")),
        "visited_segment_ids": len(fragments.get("visited_segment_ids", "")),
        "previous_queries": len(
            fragments.get("previous_scoped_query_keys", "")
        ),
        "budget_state": len(fragments.get("remaining", "")),
    }
    user_other = len(user) - sum(allocated_user.values())
    if user_other < 0:
        raise AssertionError("payload breakdown over-allocated user characters")
    raw_blocks: dict[str, tuple[int, object, int, bool]] = {
        "static_policy": (len(policy), policy, 1, True),
        "action_schema": (
            len(separator) + len(schema),
            schema,
            1,
            True,
        ),
        "tool_contracts": (0, None, 0, False),
    }
    content_counts = {
        "original_query": 1,
        "current_goal": 0,
        "open_questions": len(payload.get("open_questions", [])),
        "resolved_questions": len(payload.get("resolved_questions", [])),
        "navigation_results": len(payload.get("navigation_documents", [])),
        "evidence_text": len(payload.get("transcript_evidence", [])),
        "evidence_metadata": len(payload.get("transcript_evidence", [])),
        "latest_observation": int(
            bool(payload.get("last_action"))
            or bool(payload.get("last_observation_summary"))
        ),
        "historical_observations": 0,
        "visited_video_ids": len(payload.get("visited_video_ids", [])),
        "visited_segment_ids": len(payload.get("visited_segment_ids", [])),
        "previous_queries": len(
            payload.get("previous_scoped_query_keys", [])
        ),
        "budget_state": 1,
        "trace_or_other": 1,
    }
    for name, chars in allocated_user.items():
        raw_blocks[name] = (
            chars,
            _payload_block_value(name, payload),
            content_counts[name],
            chars > 0,
        )
    raw_blocks["trace_or_other"] = (
        user_other,
        {"structural_overhead_chars": user_other},
        1,
        user_other > 0,
    )

    blocks: dict[str, dict[str, object]] = {}
    for name, (chars, value, count, present) in raw_blocks.items():
        digest = normalized_text_hash(value) if present else stable_hash(None)
        blocks[name] = {
            "chars": chars,
            "estimated_tokens": estimated_tokens(chars),
            "token_estimation_method": ESTIMATION_METHOD,
            "repeated_from_previous_round": (
                previous_hashes.get(name) == digest if present else False
            ),
            "content_count": count,
            "normalized_hash": digest,
            "present_in_current_payload": present,
        }
        previous_hashes[name] = digest
    total = sum(int(value["chars"]) for value in blocks.values())
    if total != len(system) + len(user):
        raise AssertionError(
            f"payload breakdown does not reconcile: {total} != "
            f"{len(system) + len(user)}"
        )
    navigation_sections = [
        section
        for value in payload.get("navigation_documents", [])
        if isinstance(value, dict)
        for section in value.get("summary_sections", [])
    ]
    evidence_segment_lengths = [
        len(value.get("segment_ids", []))
        for value in payload.get("transcript_evidence", [])
        if isinstance(value, dict)
    ]
    evidence_segment_values = [
        segment_id
        for value in payload.get("transcript_evidence", [])
        if isinstance(value, dict)
        for segment_id in value.get("segment_ids", [])
    ]
    return {
        "message_chars": total,
        "estimated_tokens": estimated_tokens(total),
        "system_message_hash": stable_hash(system),
        "user_payload_hash": stable_hash(user),
        "stable_system_prefix_chars": len(system),
        "first_dynamic_field": "message[1].question",
        "blocks": blocks,
        "bounded_field_checks": {
            "summary_section_count": len(navigation_sections),
            "summary_section_max_chars": max(
                (len(value) for value in navigation_sections), default=0
            ),
            "summary_section_total_chars": sum(
                len(value) for value in navigation_sections
            ),
            "evidence_quote_max_chars": max(
                (
                    len(str(value.get("quote", "")))
                    for value in payload.get("transcript_evidence", [])
                    if isinstance(value, dict)
                ),
                default=0,
            ),
            "evidence_segment_ids_max_count": max(
                evidence_segment_lengths, default=0
            ),
            "evidence_segment_ids_total_count": len(
                evidence_segment_values
            ),
            "evidence_segment_ids_total_chars": sum(
                len(str(value)) for value in evidence_segment_values
            ),
            "navigation_description_max_chars": max(
                (
                    len(str(value.get("description", "")))
                    for value in payload.get("navigation_documents", [])
                    if isinstance(value, dict)
                ),
                default=0,
            ),
            "navigation_matched_excerpt_max_chars": max(
                (
                    len(str(value.get("matched_excerpt", "")))
                    for value in payload.get("navigation_documents", [])
                    if isinstance(value, dict)
                ),
                default=0,
            ),
            "latest_observation_max_chars": len(
                str(payload.get("last_observation_summary", ""))
            ),
            "visited_video_count": len(payload.get("visited_video_ids", [])),
            "visited_segment_count": len(
                payload.get("visited_segment_ids", [])
            ),
            "previous_query_count": len(
                payload.get("previous_scoped_query_keys", [])
            ),
        },
    }


def _payload_block_value(name: str, payload: dict[str, object]) -> object:
    mapping: dict[str, object] = {
        "original_query": payload.get("question"),
        "current_goal": None,
        "open_questions": payload.get("open_questions"),
        "resolved_questions": payload.get("resolved_questions"),
        "navigation_results": payload.get("navigation_documents"),
        "evidence_text": [
            value.get("quote")
            for value in payload.get("transcript_evidence", [])
            if isinstance(value, dict)
        ],
        "evidence_metadata": [
            {key: item for key, item in value.items() if key != "quote"}
            for value in payload.get("transcript_evidence", [])
            if isinstance(value, dict)
        ],
        "latest_observation": {
            "last_action": payload.get("last_action"),
            "last_observation_summary": payload.get(
                "last_observation_summary"
            ),
        },
        "historical_observations": None,
        "visited_video_ids": payload.get("visited_video_ids"),
        "visited_segment_ids": payload.get("visited_segment_ids"),
        "previous_queries": payload.get("previous_scoped_query_keys"),
        "budget_state": payload.get("remaining"),
    }
    return mapping[name]


def audit_deep_payload(application: Application, case: dict[str, Any]) -> dict[str, object]:
    service = application.ask_service.deep_service
    if service is None:
        raise RuntimeError("Deep Search is unavailable")
    capture = CaptureDecisionProvider()
    service.graph.decision_service.provider_factory = lambda role: capture
    started = service.clock()
    state = service._initial_state(
        "h0_scripted_payload_audit",
        AskRequest(query=case["query"], mode="deep"),
        started,
    )
    final_state: DeepSearchState = service.graph.run(state)
    previous_hashes: dict[str, str] = {}
    rounds = [
        {
            "round": index,
            "decision_kind": call["decision_kind"],
            **_breakdown_round(
                call["messages"],  # type: ignore[arg-type]
                previous_hashes,
            ),
        }
        for index, call in enumerate(capture.calls, start=1)
    ]
    top_growth = Counter()
    if rounds:
        first_blocks = rounds[0]["blocks"]
        last_blocks = rounds[-1]["blocks"]
        for key, value in last_blocks.items():
            growth = int(value["chars"]) - int(first_blocks[key]["chars"])
            top_growth[key] = growth
    return {
        "payload_source": "scripted_actions_with_real_local_tools",
        "case_id": case["case_id"],
        "decision_rounds": len(capture.calls),
        "tool_calls": final_state["tool_calls"],
        "decision_sequence": [
            str(value["decision_kind"]) for value in capture.calls
        ],
        "termination_reason": final_state["termination_reason"],
        "evidence_span_count": len(final_state["evidence_spans"]),
        "runtime_visited_video_count": len(
            final_state["visited_video_ids"]
        ),
        "runtime_visited_segment_count": len(
            final_state["visited_segment_ids"]
        ),
        "rounds": rounds,
        "top_growth_sources_first_to_last": [
            {"block": key, "growth_chars": value}
            for key, value in top_growth.most_common(5)
        ],
        "current_payload_absences": {
            "tool_contracts": True,
            "current_goal": True,
            "historical_observations": True,
            "trace_payload": True,
        },
    }


def real_usage_calibration() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    seen: set[tuple[str, int, int]] = set()
    for path in REAL_USAGE_PATHS:
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload.get("results", []):
            if row.get("mode") != "deep":
                continue
            usage = (row.get("provider_usage") or {}).get("agent_action")
            if not isinstance(usage, list):
                continue
            for round_index, item in enumerate(usage, start=1):
                if not isinstance(item, dict):
                    continue
                prompt_tokens = item.get("prompt_tokens")
                if not isinstance(prompt_tokens, int):
                    continue
                key = (str(row.get("case_id")), round_index, prompt_tokens)
                if key in seen:
                    continue
                seen.add(key)
                cached = item.get("prompt_cache_hit_tokens")
                if cached is None and isinstance(
                    item.get("prompt_tokens_details"), dict
                ):
                    cached = item["prompt_tokens_details"].get("cached_tokens")
                result.append(
                    {
                        "case_id": row.get("case_id"),
                        "round": round_index,
                        "prompt_tokens": prompt_tokens,
                        "cache_hit_tokens": cached,
                        "cache_miss_tokens": item.get(
                            "prompt_cache_miss_tokens"
                        ),
                    }
                )
    return result


def capture_variant_body(
    *,
    model: str,
    messages: list[dict[str, str]],
    variant: ProviderVariant,
) -> dict[str, object]:
    provider = OpenAICompatibleProvider(
        base_url="https://h0.invalid/v1",
        api_key="dry-run-placeholder",
        model=model,
        thinking_enabled=variant.thinking,
        reasoning_effort=variant.reasoning_effort,
    )
    _CaptureHTTPClient.bodies = []
    with patch("shiliu.llm.httpx.Client", _CaptureHTTPClient):
        provider.generate_structured(
            role="grounded_answer",
            messages=messages,
            response_schema=GroundedAnswerDraft,
            max_tokens=4096,
        )
    if len(_CaptureHTTPClient.bodies) != 1:
        raise AssertionError("dry-run provider body count changed")
    return _CaptureHTTPClient.bodies[0]


def variant_body_audit(
    model: str, fixed_requests: list[FixedRequest]
) -> dict[str, object]:
    allowed_variant_fields = {"thinking", "reasoning_effort", "temperature"}
    rows = []
    for request in fixed_requests:
        bodies = {
            variant.name: capture_variant_body(
                model=model,
                messages=request.messages,
                variant=variant,
            )
            for variant in LIVE_VARIANTS
        }
        stripped = {
            name: {
                key: value
                for key, value in body.items()
                if key not in allowed_variant_fields
            }
            for name, body in bodies.items()
        }
        rows.append(
            {
                "request_id": request.case_id,
                "non_variant_body_identical": (
                    stripped["baseline"] == stripped["thinking_off"]
                ),
                "non_variant_body_hash": stable_hash(
                    stripped["baseline"]
                ),
                "baseline_variant_fields": {
                    key: bodies["baseline"].get(key)
                    for key in sorted(allowed_variant_fields)
                    if key in bodies["baseline"]
                },
                "thinking_off_variant_fields": {
                    key: bodies["thinking_off"].get(key)
                    for key in sorted(allowed_variant_fields)
                    if key in bodies["thinking_off"]
                },
            }
        )
    return {
        "comparison_unit": (
            "configuration_combination_not_isolated_thinking"
        ),
        "allowed_variant_fields": sorted(allowed_variant_fields),
        "rows": rows,
    }


def deterministic_investigation() -> dict[str, object]:
    cases = _load_manifest()
    with snapshot_application() as application:
        fast_rows: list[FastAudit] = []
        fixed_by_id: dict[str, FixedRequest] = {}
        for case in cases:
            audit, fixed = audit_fast_case(application, case)
            fast_rows.append(audit)
            fixed_by_id[fixed.case_id] = fixed
        fixed_requests = [
            fixed_by_id[case_id] for case_id in FIXED_REQUEST_CASES
        ]
        deep = audit_deep_payload(
            application, _case_by_id(cases, "contextual_tool_failure")
        )
        variant_audit = variant_body_audit(
            application.config.model_for("grounded_answer"),
            fixed_requests,
        )
    schedule = trial_schedule()
    result = {
        "h0_mode": "deterministic_only_no_provider",
        "provider_calls": 0,
        "end_to_end_calls": 0,
        "token_estimation_method": ESTIMATION_METHOD,
        "fixed_requests": [
            value.bounded_summary() for value in fixed_requests
        ],
        "fixed_request_hash_trials": {
            value.case_id: [value.request_hash] * 3
            for value in fixed_requests
        },
        "trial_schedule": schedule,
        "configuration_body_audit": variant_audit,
        "deep_payload_audit": deep,
        "real_usage_calibration": real_usage_calibration(),
        "fast_context_diagnostics": [
            asdict(value) for value in fast_rows
        ],
        "privacy": {
            "full_messages_written": False,
            "full_evidence_context_written": False,
            "raw_response_written": False,
            "api_key_loaded": False,
            "authorization_header_written": False,
            "result_file_written": False,
        },
    }
    assert_bounded_output(result)
    return result


def assert_bounded_output(value: object) -> None:
    serialized = canonical_json(value)
    forbidden = (
        "Authorization",
        "Bearer ",
        '"messages"',
        '"model_context"',
        '"quote_text"',
        '"api_key"',
        '"raw_response"',
    )
    matches = [token for token in forbidden if token in serialized]
    if matches:
        raise AssertionError(f"bounded output contains forbidden fields: {matches}")


CHECKPOINT_FORBIDDEN_KEYS = {
    "answer",
    "answer_blocks",
    "api_key",
    "authorization",
    "context",
    "draft",
    "messages",
    "model_context",
    "prompt",
    "query",
    "quote_text",
    "raw_response",
    "transcript",
}


def _checkpoint_private_strings(
    fixed_requests: Iterable[FixedRequest],
) -> tuple[str, ...]:
    values: list[str] = []
    for fixed in fixed_requests:
        values.append(fixed.query)
        values.extend(
            message["content"]
            for message in fixed.messages
            if message.get("content")
        )
        values.append(fixed.context.model_context)
        values.extend(
            span.quote_text for span in fixed.context.spans
        )
    return tuple(dict.fromkeys(value for value in values if value))


def assert_checkpoint_bounded(
    value: object,
    *,
    private_strings: Iterable[str] = (),
) -> None:
    def walk(item: object) -> None:
        if isinstance(item, dict):
            forbidden = CHECKPOINT_FORBIDDEN_KEYS.intersection(item)
            if forbidden:
                raise AssertionError(
                    "checkpoint contains forbidden keys: "
                    f"{sorted(forbidden)}"
                )
            for nested in item.values():
                walk(nested)
        elif isinstance(item, list):
            for nested in item:
                walk(nested)

    walk(value)
    serialized = canonical_json(value).casefold()
    leaked: list[str] = []
    for private in private_strings:
        normalized = private.strip().casefold()
        if normalized and normalized in serialized:
            leaked.append(stable_hash(normalized)[:12])
    if leaked:
        raise AssertionError(
            "checkpoint contains private material hashes: "
            f"{sorted(set(leaked))}"
        )


def _atomic_write_checkpoint(
    path: Path,
    payload: dict[str, object],
) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary_name = ""
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            os.chmod(temporary_name, 0o600)
            json.dump(
                payload,
                temporary,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
        os.chmod(path, 0o600)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _checkpoint_specification(
    fixed_requests: list[FixedRequest],
    configurations: tuple[ProviderVariant, ...],
    trials_per_configuration: int,
    consecutive_failure_limit: int,
) -> dict[str, object]:
    schedule = trial_schedule(
        tuple(value.name for value in configurations),
        trials=trials_per_configuration,
    )
    request_groups: list[dict[str, object]] = []
    for fixed in fixed_requests:
        counts: Counter[str] = Counter()
        expected_trial_ids: list[str] = []
        for configuration_name in schedule:
            counts[configuration_name] += 1
            expected_trial_ids.append(
                f"{fixed.case_id}:{configuration_name}:"
                f"{counts[configuration_name]}"
            )
        request_groups.append(
            {
                "request_id": fixed.case_id,
                "request_hash": fixed.request_hash,
                "expected_trial_ids": expected_trial_ids,
            }
        )
    identity = {
        "checkpoint_version": CHECKPOINT_VERSION,
        "request_groups": request_groups,
        "configurations": [
            value.public_configuration() for value in configurations
        ],
        "trials_per_request_configuration": trials_per_configuration,
        "consecutive_provider_failure_limit": consecutive_failure_limit,
        "maximum_logical_provider_invocations": (
            MAX_LOGICAL_PROVIDER_INVOCATIONS
        ),
        "maximum_transport_http_attempts": MAX_TRANSPORT_HTTP_ATTEMPTS,
    }
    return {
        **identity,
        "campaign_id": stable_hash(identity),
        "expected_trial_count": len(fixed_requests) * len(schedule),
    }


class ReplayCheckpointStore:
    """Atomic bounded WAL; it never receives or serializes private bodies."""

    def __init__(
        self,
        path: Path,
        *,
        specification: dict[str, object],
        private_strings: Iterable[str],
    ) -> None:
        self.path = path
        self.specification = specification
        self._private_strings = tuple(private_strings)
        self.resumed = path.is_file()
        if self.resumed:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ReplayRecoveryBlocked("checkpoint root is not an object")
            self.data: dict[str, object] = value
            assert_checkpoint_bounded(
                self.data, private_strings=self._private_strings
            )
            if self.data.get("campaign_id") != specification["campaign_id"]:
                raise ReplayRecoveryBlocked(
                    "checkpoint campaign identity does not match frozen matrix"
                )
            self._recover_existing_process_state()
        else:
            groups = [
                {
                    **group,
                    "state": "pending",
                    "completed_trial_ids": [],
                    "rows": [],
                    "quality_reviews": [],
                }
                for group in specification["request_groups"]  # type: ignore[union-attr]
            ]
            self.data = {
                **specification,
                "status": "active",
                "matrix_complete": False,
                "completed_trial_count": 0,
                "completed_trial_ids": [],
                "provider_logical_invocations_completed": 0,
                "transport_http_attempts_completed": 0,
                "consecutive_provider_failures": 0,
                "in_flight_trial": None,
                "stop_reason": None,
                "groups": groups,
                "recovery_events": [],
                "privacy": {
                    "private_bodies_persisted": False,
                    "prompt_persisted": False,
                    "answer_body_persisted": False,
                    "transcript_evidence_persisted": False,
                    "secret_credential_persisted": False,
                    "provider_raw_body_persisted": False,
                },
            }
            self._persist()

    def _persist(
        self,
        *,
        extra_private_strings: Iterable[str] = (),
    ) -> None:
        private = (*self._private_strings, *extra_private_strings)
        assert_checkpoint_bounded(self.data, private_strings=private)
        _atomic_write_checkpoint(self.path, self.data)

    def _groups(self) -> list[dict[str, object]]:
        groups = self.data.get("groups")
        if not isinstance(groups, list):
            raise ReplayRecoveryBlocked("checkpoint groups are invalid")
        return groups  # type: ignore[return-value]

    def group(self, request_id: str) -> dict[str, object]:
        for group in self._groups():
            if group.get("request_id") == request_id:
                return group
        raise ReplayRecoveryBlocked(
            f"checkpoint request group is missing: {request_id}"
        )

    def _append_recovery_event(
        self, event: str, request_id: str | None
    ) -> None:
        events = self.data["recovery_events"]
        assert isinstance(events, list)
        events.append(
            {
                "event": event,
                "request_id": request_id,
                "observed_at_utc": datetime.now(timezone.utc).isoformat(
                    timespec="milliseconds"
                ),
            }
        )

    def _recover_existing_process_state(self) -> None:
        status = self.data.get("status")
        if status in {"complete", "stopped_early", "blocked_recovery"}:
            return
        in_flight = self.data.get("in_flight_trial")
        if isinstance(in_flight, dict):
            request_id = str(in_flight.get("request_id", ""))
            self.group(request_id)["state"] = "blocked_unknown_in_flight"
            self.data["status"] = "blocked_recovery"
            self.data["stop_reason"] = (
                "unknown_in_flight_trial_never_replayed"
            )
            self._append_recovery_event(
                "blocked_unknown_in_flight_trial_no_duplicate_call",
                request_id,
            )
            self._persist()
            return
        for group in self._groups():
            state = group.get("state")
            if state in {
                "collecting",
                "trials_complete_review_pending",
                "review_in_progress",
            }:
                group["state"] = (
                    "review_unrecoverable_private_drafts_not_persisted"
                )
                self.data["status"] = "blocked_recovery"
                self.data["stop_reason"] = (
                    "active_group_private_drafts_lost_no_provider_replay"
                )
                self._append_recovery_event(
                    "blocked_active_group_no_private_draft_recovery",
                    str(group.get("request_id", "")),
                )
                self._persist()
                return
        self._append_recovery_event(
            "safe_resume_after_reviewed_request_groups", None
        )
        self._persist()

    @property
    def blocked(self) -> bool:
        return self.data.get("status") == "blocked_recovery"

    @property
    def terminal(self) -> bool:
        return self.data.get("status") in {
            "complete",
            "stopped_early",
            "blocked_recovery",
        }

    def begin_trial(
        self,
        *,
        request_id: str,
        trial_id: str,
        sequence_index: int,
    ) -> None:
        if self.terminal:
            raise ReplayRecoveryBlocked(
                f"checkpoint is terminal: {self.data.get('status')}"
            )
        if self.data.get("in_flight_trial") is not None:
            raise ReplayRecoveryBlocked("another trial is already in flight")
        completed = self.data["completed_trial_ids"]
        assert isinstance(completed, list)
        if trial_id in completed:
            raise ReplayRecoveryBlocked(
                f"duplicate Provider call refused for {trial_id}"
            )
        group = self.group(request_id)
        expected = group["expected_trial_ids"]
        assert isinstance(expected, list)
        if trial_id not in expected:
            raise ReplayRecoveryBlocked(f"unexpected trial id: {trial_id}")
        completed_invocations = int(
            self.data["provider_logical_invocations_completed"]
        )
        if (
            completed_invocations
            + MAX_LOGICAL_INVOCATIONS_PER_TRIAL
            > MAX_LOGICAL_PROVIDER_INVOCATIONS
        ):
            raise ReplayRecoveryBlocked(
                "logical Provider invocation budget would be exceeded"
            )
        if (
            int(self.data["transport_http_attempts_completed"])
            + MAX_TRANSPORT_ATTEMPTS_PER_TRIAL
            > MAX_TRANSPORT_HTTP_ATTEMPTS
        ):
            raise ReplayRecoveryBlocked(
                "transport HTTP attempt budget would be exceeded"
            )
        self.data["in_flight_trial"] = {
            "trial_id": trial_id,
            "request_id": request_id,
            "sequence_index": sequence_index,
            "logical_invocation_upper_bound_reserved": (
                MAX_LOGICAL_INVOCATIONS_PER_TRIAL
            ),
            "transport_attempt_upper_bound_reserved": (
                MAX_TRANSPORT_ATTEMPTS_PER_TRIAL
            ),
            "started_at_utc": datetime.now(timezone.utc).isoformat(
                timespec="milliseconds"
            ),
        }
        if group.get("state") == "pending":
            group["state"] = "collecting"
        self._persist()

    def complete_trial(self, record: TrialRecord) -> None:
        in_flight = self.data.get("in_flight_trial")
        if not isinstance(in_flight, dict) or (
            in_flight.get("trial_id") != record.trial_id
        ):
            raise ReplayRecoveryBlocked(
                "trial completion does not match bounded in-flight WAL"
            )
        row = record.public_measurement()
        logical_invocations = int(row.get("provider_call_count") or 0)
        transport_retries = int(row.get("retry_count") or 0)
        transport_attempts = logical_invocations + transport_retries
        if not 0 <= logical_invocations <= MAX_LOGICAL_INVOCATIONS_PER_TRIAL:
            raise ReplayRecoveryBlocked(
                "trial logical Provider invocation count is out of bounds"
            )
        if not 0 <= transport_attempts <= MAX_TRANSPORT_ATTEMPTS_PER_TRIAL:
            raise ReplayRecoveryBlocked(
                "trial transport attempt count is out of bounds"
            )
        group = self.group(record.request.case_id)
        rows = group["rows"]
        completed_group = group["completed_trial_ids"]
        completed_all = self.data["completed_trial_ids"]
        assert isinstance(rows, list)
        assert isinstance(completed_group, list)
        assert isinstance(completed_all, list)
        if record.trial_id in completed_all:
            raise ReplayRecoveryBlocked(
                f"duplicate trial completion refused: {record.trial_id}"
            )
        rows.append(row)
        completed_group.append(record.trial_id)
        completed_all.append(record.trial_id)
        self.data["completed_trial_count"] = len(completed_all)
        self.data["provider_logical_invocations_completed"] = (
            int(self.data["provider_logical_invocations_completed"])
            + logical_invocations
        )
        self.data["transport_http_attempts_completed"] = (
            int(self.data["transport_http_attempts_completed"])
            + transport_attempts
        )
        self.data["in_flight_trial"] = None
        if record.provider_failed:
            self.data["consecutive_provider_failures"] = (
                int(self.data["consecutive_provider_failures"]) + 1
            )
        else:
            self.data["consecutive_provider_failures"] = 0
        expected = group["expected_trial_ids"]
        assert isinstance(expected, list)
        if completed_group == expected:
            group["state"] = "trials_complete_review_pending"
        extra_private = [
            *(
                [block.text for block in record.draft.answer_blocks]
                if record.draft is not None
                else []
            ),
            *[span.quote_text for span in record.request.context.spans],
        ]
        self._persist(extra_private_strings=extra_private)

    def prepare_group_review(self, request_id: str) -> None:
        group = self.group(request_id)
        if not group["completed_trial_ids"]:
            raise ReplayRecoveryBlocked("cannot review an empty request group")
        group["state"] = "trials_complete_review_pending"
        self._persist()

    def checkpoint_review(
        self,
        request_id: str,
        row: dict[str, object],
    ) -> None:
        group = self.group(request_id)
        reviews = group["quality_reviews"]
        assert isinstance(reviews, list)
        provisional = {
            **row,
            "checkpoint_phase": "score_captured_pending_group_finalization",
        }
        by_trial = {
            str(value.get("trial_id")): index
            for index, value in enumerate(reviews)
            if isinstance(value, dict)
        }
        trial_id = str(row["trial_id"])
        if trial_id in by_trial:
            reviews[by_trial[trial_id]] = provisional
        else:
            reviews.append(provisional)
        group["state"] = "review_in_progress"
        self._persist()

    def complete_group(
        self,
        request_id: str,
        reviews: list[dict[str, object]],
    ) -> None:
        group = self.group(request_id)
        group["quality_reviews"] = reviews
        group["state"] = "review_complete"
        if all(
            value.get("state") == "review_complete"
            for value in self._groups()
        ):
            self.data["status"] = "complete"
            self.data["matrix_complete"] = (
                int(self.data["completed_trial_count"])
                == int(self.data["expected_trial_count"])
            )
        self._persist()

    def stop_after_fail_fast(self) -> None:
        self.data["status"] = "stopped_early"
        self.data["matrix_complete"] = False
        self.data["stop_reason"] = (
            "campaign_fail_fast_after_"
            f"{self.data['consecutive_provider_failures']}"
            "_consecutive_provider_failures"
        )
        self._persist()

    def bounded_payload(self) -> dict[str, object]:
        rows: list[dict[str, object]] = []
        reviews: list[dict[str, object]] = []
        completed_groups: list[str] = []
        group_states: list[dict[str, object]] = []
        for group in self._groups():
            group_rows = group["rows"]
            group_reviews = group["quality_reviews"]
            assert isinstance(group_rows, list)
            assert isinstance(group_reviews, list)
            rows.extend(group_rows)
            reviews.extend(group_reviews)
            request_id = str(group["request_id"])
            if group.get("state") == "review_complete":
                completed_groups.append(request_id)
            group_states.append(
                {
                    "request_id": request_id,
                    "request_hash": group["request_hash"],
                    "state": group["state"],
                    "completed_trial_count": len(group_rows),
                    "quality_review_count": len(group_reviews),
                }
            )
        in_flight = self.data.get("in_flight_trial")
        reserved_logical = (
            int(in_flight["logical_invocation_upper_bound_reserved"])
            if isinstance(in_flight, dict)
            else 0
        )
        completed_logical = int(
            self.data["provider_logical_invocations_completed"]
        )
        payload = {
            "checkpoint_version": self.data["checkpoint_version"],
            "campaign_id": self.data["campaign_id"],
            "checkpoint_path": str(self.path),
            "status": self.data["status"],
            "expected_trial_count": self.data["expected_trial_count"],
            "completed_trial_count": self.data["completed_trial_count"],
            "matrix_complete": self.data["matrix_complete"],
            "completed_trial_ids": list(self.data["completed_trial_ids"]),  # type: ignore[arg-type]
            "completed_request_groups": completed_groups,
            "group_states": group_states,
            "provider_logical_invocations_completed": completed_logical,
            "provider_logical_invocations_upper_bound_committed": (
                completed_logical + reserved_logical
            ),
            "remaining_logical_invocation_cap": (
                MAX_LOGICAL_PROVIDER_INVOCATIONS
                - completed_logical
                - reserved_logical
            ),
            "transport_http_attempts_completed": self.data[
                "transport_http_attempts_completed"
            ],
            "consecutive_provider_failures": self.data[
                "consecutive_provider_failures"
            ],
            "stop_reason": self.data["stop_reason"],
            "in_flight_trial": in_flight,
            "recovery_events": list(self.data["recovery_events"]),  # type: ignore[arg-type]
            "rows": rows,
            "quality_reviews": reviews,
            "privacy": dict(self.data["privacy"]),  # type: ignore[arg-type]
        }
        assert_checkpoint_bounded(
            payload, private_strings=self._private_strings
        )
        return payload


def run_campaign(
    *,
    fixed_requests: list[FixedRequest],
    execute_trial: Callable[
        [FixedRequest, ProviderVariant, int, int], TrialRecord
    ],
    configurations: tuple[ProviderVariant, ...] = LIVE_VARIANTS,
    trials_per_configuration: int = 3,
    consecutive_failure_limit: int = CONSECUTIVE_PROVIDER_FAILURE_LIMIT,
) -> CampaignResult:
    if consecutive_failure_limit <= 0:
        raise ValueError("consecutive failure limit must be positive")
    configuration_names = tuple(value.name for value in configurations)
    schedule = trial_schedule(
        configuration_names, trials=trials_per_configuration
    )
    by_name = {value.name: value for value in configurations}
    expected = len(fixed_requests) * len(schedule)
    completed: list[TrialRecord] = []
    consecutive_failures = 0
    sequence_index = 0
    stopped = False
    stop_reason: str | None = None
    per_group_counts: Counter[tuple[str, str]] = Counter()
    for fixed in fixed_requests:
        for configuration_name in schedule:
            sequence_index += 1
            group_key = (fixed.case_id, configuration_name)
            per_group_counts[group_key] += 1
            record = execute_trial(
                fixed,
                by_name[configuration_name],
                sequence_index,
                per_group_counts[group_key],
            )
            completed.append(record)
            if record.provider_failed:
                consecutive_failures += 1
            else:
                consecutive_failures = 0
            if consecutive_failures >= consecutive_failure_limit:
                stopped = True
                stop_reason = (
                    "campaign_fail_fast_after_"
                    f"{consecutive_failures}_consecutive_provider_failures"
                )
                break
        if stopped:
            break
    return CampaignResult(
        trials=tuple(completed),
        expected_trial_count=expected,
        consecutive_failure_limit=consecutive_failure_limit,
        stopped_early=stopped,
        stop_reason=stop_reason,
    )


def _risk_key(record: TrialRecord) -> tuple[int, int, int, int]:
    validation_errors = record.measurement.get("validation_error_codes")
    return (
        1 if record.draft is None else 0,
        1 if record.measurement.get("repair_required") else 0,
        len(validation_errors) if isinstance(validation_errors, list) else 0,
        int(record.measurement.get("retry_count") or 0),
    )


def _median_latency_record(records: list[TrialRecord]) -> TrialRecord:
    with_latency = [
        value
        for value in records
        if isinstance(value.measurement.get("latency_ms"), (int, float))
    ]
    if not with_latency:
        return records[0]
    ordered = sorted(
        with_latency,
        key=lambda value: (
            float(value.measurement["latency_ms"]),
            value.trial_id,
        ),
    )
    return ordered[len(ordered) // 2]


def _review_material(
    record: TrialRecord,
    materializer: TranscriptEvidenceMaterializer,
) -> QualityReviewMaterial:
    # Rebuild/validate every allowed Citation from the current Source Version,
    # not from a retained review excerpt. This also gives insufficient/failure
    # trials the full bounded Evidence Context needed for status/coverage review.
    current: list[TranscriptEvidenceSpan] = []
    by_id = {
        value.citation_id: value for value in record.request.context.spans
    }
    for citation_id in record.request.context.citation_allowlist:
        span = by_id.get(citation_id)
        if span is None:
            raise AssertionError(
                "citation allowlist is not reconstructable from fixed context"
            )
        materializer.validate_current(span)
        current.append(span)
    private_value = {
        "trial_id": record.trial_id,
        "query": record.request.query,
        "draft": (
            record.draft.model_dump(mode="json")
            if record.draft is not None
            else None
        ),
        "cited_ids": list(record.citation_ids),
        "current_full_evidence": [
            value.model_dump(mode="json") for value in current
        ],
    }
    return QualityReviewMaterial(
        trial_id=record.trial_id,
        query=record.request.query,
        draft=record.draft,
        cited_ids=record.citation_ids,
        current_full_evidence=tuple(current),
        material_hash=stable_hash(private_value),
    )


def _score_risk(scores: QualityScores) -> tuple[int, int, int, int]:
    rank = {"pass": 0, "partial": 1, "fail": 2}
    values = (
        scores.supportedness,
        scores.usefulness,
        scores.coverage,
        scores.status_honesty,
    )
    return (
        sum(rank[value] for value in values),
        rank[scores.supportedness],
        rank[scores.status_honesty],
        rank[scores.coverage],
    )


def _bounded_review_reason(
    value: str, material: QualityReviewMaterial
) -> str:
    normalized = " ".join(value.split())[:300]
    private_texts = [
        material.query,
        *(
            [block.text for block in material.draft.answer_blocks]
            if material.draft is not None
            else []
        ),
        *[span.quote_text for span in material.current_full_evidence],
    ]
    normalized_casefold = normalized.casefold()
    if normalized_casefold and any(
        " ".join(text.split()).casefold() in normalized_casefold
        for text in private_texts
        if text.strip()
    ):
        return (
            "Reviewer reason withheld because it reproduced a complete "
            "private prompt, answer, or Evidence span."
        )
    return normalized


def _public_review_row(
    *,
    record: TrialRecord,
    material: QualityReviewMaterial,
    scores: QualityScores,
    selection_reasons: Iterable[str],
) -> dict[str, object]:
    reason = _bounded_review_reason(scores.reason_summary, material)
    return {
        "trial_id": record.trial_id,
        "request_id": record.request.case_id,
        "configuration_id": record.configuration.name,
        "selection_reasons": sorted(selection_reasons),
        "supportedness": scores.supportedness,
        "usefulness": scores.usefulness,
        "coverage": scores.coverage,
        "status_honesty": scores.status_honesty,
        "reason_summary": reason,
        "reason_summary_hash": stable_hash(scores.reason_summary),
        "review_material_hash": material.material_hash,
        "full_current_evidence_reconstructed": True,
        "reconstructed_citation_count": len(
            material.current_full_evidence
        ),
        "cited_id_count": len(material.cited_ids),
        "full_answer_or_evidence_persisted": False,
    }


def conduct_quality_reviews(
    campaign: CampaignResult,
    *,
    materializer: TranscriptEvidenceMaterializer,
    reviewer: QualityReviewer,
    on_review: (
        Callable[[str, dict[str, object]], None] | None
    ) = None,
) -> list[dict[str, object]]:
    groups: dict[tuple[str, str], list[TrialRecord]] = {}
    for record in campaign.trials:
        groups.setdefault(
            (record.request.case_id, record.configuration.name), []
        ).append(record)

    public_reviews: list[dict[str, object]] = []
    for (request_id, configuration_id), records in groups.items():
        roles: dict[str, set[str]] = {}

        def add_role(record: TrialRecord, role: str) -> None:
            roles.setdefault(record.trial_id, set()).add(role)

        median = _median_latency_record(records)
        add_role(median, "median_latency")
        risk_candidate = max(records, key=_risk_key)
        add_role(risk_candidate, "deterministic_risk_or_failure_candidate")
        if len({value.behavior_hash for value in records}) > 1:
            for record in records:
                add_role(record, "behavior_divergence_review_all")

        reviewed: list[
            tuple[TrialRecord, QualityReviewMaterial, QualityScores]
        ] = []
        selected_ids = set(roles)
        for record in records:
            if record.trial_id not in selected_ids:
                continue
            material = _review_material(record, materializer)
            scores = reviewer(material)
            reviewed.append((record, material, scores))
            if on_review is not None:
                on_review(
                    request_id,
                    _public_review_row(
                        record=record,
                        material=material,
                        scores=scores,
                        selection_reasons=roles[record.trial_id],
                    ),
                )
        if not reviewed:
            raise AssertionError("quality review selection is empty")
        worst_record, _, _ = max(
            reviewed,
            key=lambda value: (
                _score_risk(value[2]),
                _risk_key(value[0]),
            ),
        )
        add_role(worst_record, "worst_quality_or_failure")

        for record, material, scores in reviewed:
            public_reviews.append(
                _public_review_row(
                    record=record,
                    material=material,
                    scores=scores,
                    selection_reasons=roles[record.trial_id],
                )
            )
    return public_reviews


def _quality_review_with_streams(
    material: QualityReviewMaterial,
    terminal_in: Any,
    terminal_out: Any,
) -> QualityScores:
    terminal_out.write(
        "\n=== H0 ephemeral quality review "
        f"{material.trial_id} ===\nQuestion:\n{material.query}\n"
    )
    if material.draft is None:
        terminal_out.write("Final structured draft: <provider failure>\n")
    else:
        terminal_out.write(
            "Final structured draft:\n"
            + json.dumps(
                material.draft.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
    terminal_out.write("Current full Evidence reconstructed by Citation ID:\n")
    for span in material.current_full_evidence:
        marker = "CITED" if span.citation_id in material.cited_ids else "AVAILABLE"
        terminal_out.write(
            f"\n[{marker}] {span.citation_id} "
            f"{span.start_time:.2f}-{span.end_time:.2f}\n"
            f"{span.quote_text}\n"
        )

    def ask_score(label: str) -> str:
        while True:
            terminal_out.write(f"{label} (pass/partial/fail): ")
            terminal_out.flush()
            value = terminal_in.readline().strip().casefold()
            if value in QUALITY_VALUES:
                return value
            terminal_out.write("Invalid score.\n")

    scores = {
        "supportedness": ask_score("supportedness"),
        "usefulness": ask_score("usefulness"),
        "coverage": ask_score("coverage"),
        "status_honesty": ask_score("status_honesty"),
    }
    terminal_out.write("Bounded reason summary: ")
    terminal_out.flush()
    reason = terminal_in.readline().strip()
    return QualityScores(**scores, reason_summary=reason)


def _tty_preflight_with_streams(
    terminal_in: Any,
    terminal_out: Any,
    *,
    challenge: str,
) -> TTYPreflightProof:
    terminal_out.write(
        "\nH0 quality-review TTY preflight. No Provider call has started.\n"
        f"Type exactly: {challenge}\n> "
    )
    terminal_out.flush()
    response = terminal_in.readline()
    if not response or response.strip() != challenge:
        raise RuntimeError(
            "quality-review TTY preflight challenge was not confirmed"
        )
    terminal_out.write(
        "H0 quality-review TTY preflight passed; read/write roundtrip OK.\n"
    )
    terminal_out.flush()
    proof = TTYPreflightProof(
        process_id=os.getpid(),
        verified_at_utc=datetime.now(timezone.utc).isoformat(
            timespec="milliseconds"
        ),
        challenge_hash=stable_hash(challenge),
        read_write_roundtrip=True,
    )
    _TTY_PREFLIGHT_PROOFS.add((proof.process_id, proof.challenge_hash))
    return proof


def preflight_quality_review_tty() -> TTYPreflightProof:
    if not sys.stdin.isatty():
        raise RuntimeError("quality-review TTY preflight requires a TTY")
    challenge = (
        f"{TTY_PREFLIGHT_PREFIX}-"
        f"{stable_hash([os.getpid(), datetime.now(timezone.utc).isoformat()])[:8]}"
    )
    with (
        open("/dev/tty", "r", encoding="utf-8") as terminal_in,
        open("/dev/tty", "w", encoding="utf-8") as terminal_out,
    ):
        if not terminal_in.isatty() or not terminal_out.isatty():
            raise RuntimeError(
                "quality-review TTY preflight did not open real TTY streams"
            )
        return _tty_preflight_with_streams(
            terminal_in,
            terminal_out,
            challenge=challenge,
        )


def _consume_tty_preflight(proof: TTYPreflightProof) -> None:
    if not proof.valid_for_current_process:
        raise ValueError(
            "live replay requires a real current-process TTY preflight"
        )
    _TTY_PREFLIGHT_PROOFS.remove((proof.process_id, proof.challenge_hash))


def terminal_quality_reviewer(
    material: QualityReviewMaterial,
) -> QualityScores:
    """Ephemeral TTY review; no full answer/Evidence is serialized or saved."""

    if not sys.stdin.isatty():
        raise RuntimeError("interactive quality review requires a TTY")
    # A PTY is not seekable, so use independent one-way streams instead of
    # opening /dev/tty as a bidirectional TextIOWrapper.
    with (
        open("/dev/tty", "r", encoding="utf-8") as terminal_in,
        open("/dev/tty", "w", encoding="utf-8") as terminal_out,
    ):
        return _quality_review_with_streams(
            material, terminal_in, terminal_out
        )


def _live_provider(
    application: Application,
    variant: ProviderVariant,
    api_key: str,
) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        base_url=application.config.llm_base_url,
        api_key=api_key,
        model=application.config.model_for("grounded_answer"),
        timeout_seconds=180,
        thinking_enabled=variant.thinking,
        reasoning_effort=variant.reasoning_effort,
    )


def _execute_live_trial(
    *,
    application: Application,
    api_key: str,
    fixed: FixedRequest,
    configuration: ProviderVariant,
    sequence_index: int,
    configuration_trial_index: int,
) -> TrialRecord:
    provider = _live_provider(application, configuration, api_key)
    materializer = TranscriptEvidenceMaterializer(application.db)
    service = GroundedAnswerService(
        lambda role, value=provider: value,
        materializer,
    )
    if _answer_messages(
        query=fixed.query, context=fixed.context
    ) != fixed.messages:
        raise AssertionError("fixed request changed before live execution")
    started_at = datetime.now(timezone.utc).isoformat(
        timespec="milliseconds"
    )
    result: GroundedAnswerResult = service.answer(
        query=fixed.query,
        context=fixed.context,
    )
    usage = [dict(value) for value in result.usage]
    usage_metrics = extract_usage_metrics(usage)
    draft = result.draft
    citation_ids = tuple(
        dict.fromkeys(
            citation_id
            for block in (draft.answer_blocks if draft is not None else [])
            for citation_id in block.citation_ids
        )
    )
    trial_id = (
        f"{fixed.case_id}:{configuration.name}:"
        f"{configuration_trial_index}"
    )
    measurement: dict[str, object] = {
        "request_id": fixed.case_id,
        "request_hash": fixed.request_hash,
        "sequence_index": sequence_index,
        "configuration_trial_index": configuration_trial_index,
        "started_at_utc": started_at,
        "model": provider.model,
        "role": "grounded_answer",
        "message_chars": fixed.message_chars,
        "context_chars": fixed.context_chars,
        **usage_metrics,
        "finish_reason": next(
            (
                value.get("finish_reason")
                for value in reversed(usage)
                if value.get("finish_reason") is not None
            ),
            None,
        ),
        "schema_valid_first_try": (
            not result.repair_used and draft is not None
        ),
        "repair_required": result.repair_used,
        "repair_succeeded": result.repair_used and draft is not None,
        "provider_call_count": result.provider_call_count,
        "retry_count": result.transport_retry_count,
        "status": draft.status if draft is not None else None,
        "answer_block_count": (
            len(draft.answer_blocks) if draft is not None else 0
        ),
        "citation_count": len(citation_ids),
        "validation_error_codes": [
            value.code
            for value in (
                *result.initial_validation_errors,
                *result.validation_errors,
            )
        ],
        "provider_error_code": result.provider_error_code,
    }
    return TrialRecord(
        trial_id=trial_id,
        request=fixed,
        configuration=configuration,
        measurement=measurement,
        draft=draft,
        citation_ids=citation_ids,
    )


def run_checkpointed_campaign(
    *,
    fixed_requests: list[FixedRequest],
    execute_trial: Callable[
        [FixedRequest, ProviderVariant, int, int], TrialRecord
    ],
    materializer: TranscriptEvidenceMaterializer,
    reviewer: QualityReviewer,
    checkpoint_path: Path,
    configurations: tuple[ProviderVariant, ...] = LIVE_VARIANTS,
    trials_per_configuration: int = 3,
    consecutive_failure_limit: int = CONSECUTIVE_PROVIDER_FAILURE_LIMIT,
    event_hook: (
        Callable[[str, dict[str, object]], None] | None
    ) = None,
) -> dict[str, object]:
    specification = _checkpoint_specification(
        fixed_requests,
        configurations,
        trials_per_configuration,
        consecutive_failure_limit,
    )
    checkpoint = ReplayCheckpointStore(
        checkpoint_path,
        specification=specification,
        private_strings=_checkpoint_private_strings(fixed_requests),
    )
    if checkpoint.terminal:
        return checkpoint.bounded_payload()

    schedule = trial_schedule(
        tuple(value.name for value in configurations),
        trials=trials_per_configuration,
    )
    by_name = {value.name: value for value in configurations}
    fail_fast = False

    def emit(event: str, details: dict[str, object]) -> None:
        if event_hook is not None:
            event_hook(event, details)

    for request_index, fixed in enumerate(fixed_requests):
        group = checkpoint.group(fixed.case_id)
        if group.get("state") == "review_complete":
            continue
        if group.get("state") != "pending":
            raise ReplayRecoveryBlocked(
                "unsafe request-group state reached Provider loop: "
                f"{group.get('state')}"
            )
        counts: Counter[str] = Counter()
        group_records: list[TrialRecord] = []
        for offset, configuration_name in enumerate(schedule, start=1):
            counts[configuration_name] += 1
            trial_id = (
                f"{fixed.case_id}:{configuration_name}:"
                f"{counts[configuration_name]}"
            )
            sequence_index = request_index * len(schedule) + offset
            checkpoint.begin_trial(
                request_id=fixed.case_id,
                trial_id=trial_id,
                sequence_index=sequence_index,
            )
            emit(
                "provider_wal_persisted",
                {
                    "request_id": fixed.case_id,
                    "trial_id": trial_id,
                },
            )
            record = execute_trial(
                fixed,
                by_name[configuration_name],
                sequence_index,
                counts[configuration_name],
            )
            if record.trial_id != trial_id:
                raise ReplayRecoveryBlocked(
                    "Provider result trial identity differs from WAL"
                )
            emit(
                "provider_returned_before_checkpoint",
                {
                    "request_id": fixed.case_id,
                    "trial_id": trial_id,
                },
            )
            checkpoint.complete_trial(record)
            group_records.append(record)
            emit(
                "trial_checkpointed",
                {
                    "request_id": fixed.case_id,
                    "trial_id": trial_id,
                },
            )
            if (
                int(checkpoint.data["consecutive_provider_failures"])
                >= consecutive_failure_limit
            ):
                fail_fast = True
                break

        checkpoint.prepare_group_review(fixed.case_id)
        emit(
            "group_review_pending",
            {
                "request_id": fixed.case_id,
                "completed_trial_count": len(group_records),
            },
        )
        group_campaign = CampaignResult(
            trials=tuple(group_records),
            expected_trial_count=len(schedule),
            consecutive_failure_limit=consecutive_failure_limit,
            stopped_early=fail_fast,
            stop_reason=(
                "campaign_fail_fast_pending_group_review"
                if fail_fast
                else None
            ),
        )

        def checkpoint_one_review(
            request_id: str,
            row: dict[str, object],
        ) -> None:
            checkpoint.checkpoint_review(request_id, row)
            emit(
                "quality_review_checkpointed",
                {
                    "request_id": request_id,
                    "trial_id": row["trial_id"],
                },
            )

        reviews = conduct_quality_reviews(
            group_campaign,
            materializer=materializer,
            reviewer=reviewer,
            on_review=checkpoint_one_review,
        )
        checkpoint.complete_group(fixed.case_id, reviews)
        emit(
            "group_review_complete",
            {
                "request_id": fixed.case_id,
                "quality_review_count": len(reviews),
            },
        )
        if fail_fast:
            checkpoint.stop_after_fail_fast()
            break
    return checkpoint.bounded_payload()


def run_live_replay(
    authorization: str,
    *,
    reviewer: QualityReviewer | None = None,
    tty_preflight: TTYPreflightProof | None = None,
    checkpoint_path: Path = DEFAULT_CHECKPOINT_PATH,
) -> dict[str, object]:
    if authorization != LIVE_AUTHORIZATION_PHRASE:
        raise PermissionError(
            "live replay requires the exact explicit-authorization phrase"
        )
    if reviewer is None:
        raise ValueError(
            "live replay requires an in-process quality reviewer"
        )
    if tty_preflight is None:
        raise ValueError(
            "live replay requires a real current-process TTY preflight"
        )
    _consume_tty_preflight(tty_preflight)
    cases = _load_manifest()
    with snapshot_application() as application:
        fixed_by_id = {
            fixed.case_id: fixed
            for case in cases
            for _, fixed in [audit_fast_case(application, case)]
            if fixed.case_id in FIXED_REQUEST_CASES
        }
        fixed_requests = [
            fixed_by_id[case_id] for case_id in FIXED_REQUEST_CASES
        ]
        api_key: str | None = None

        def execute(
            fixed: FixedRequest,
            configuration: ProviderVariant,
            sequence: int,
            trial_index: int,
        ) -> TrialRecord:
            nonlocal api_key
            if api_key is None:
                api_key = load_api_key(application.config.api_key_ref)
            return _execute_live_trial(
                application=application,
                api_key=api_key,
                fixed=fixed,
                configuration=configuration,
                sequence_index=sequence,
                configuration_trial_index=trial_index,
            )

        campaign = run_checkpointed_campaign(
            fixed_requests=fixed_requests,
            execute_trial=execute,
            materializer=TranscriptEvidenceMaterializer(application.db),
            reviewer=reviewer,
            checkpoint_path=checkpoint_path,
        )
    payload = {
        "h0_mode": "authorized_fixed_request_live_replay",
        "comparison_unit": (
            "configuration_combination; results do not isolate Thinking as "
            "a single causal variable because thinking, reasoning_effort, "
            "and temperature differ together"
        ),
        "configurations": [
            value.public_configuration() for value in LIVE_VARIANTS
        ],
        "campaign": campaign,
        "logical_trials": campaign["completed_trial_count"],
        "maximum_logical_provider_invocations_including_repair": (
            MAX_LOGICAL_PROVIDER_INVOCATIONS
        ),
        "maximum_transport_http_attempts_including_one_retry_each": (
            MAX_TRANSPORT_HTTP_ATTEMPTS
        ),
        "rows": campaign["rows"],
        "quality_reviews": campaign["quality_reviews"],
        "privacy": {
            "final_structured_drafts_retained_in_process_only": True,
            "full_current_evidence_reconstructed_in_process_only": True,
            "full_answer_or_evidence_persisted": False,
            "report_contains_scores_reason_summaries_and_hashes_only": True,
        },
    }
    assert_bounded_output(payload)
    return payload


def run_end_to_end(
    authorization: str,
    variants: tuple[str, ...],
) -> dict[str, object]:
    if authorization != E2E_AUTHORIZATION_PHRASE:
        raise PermissionError(
            "end-to-end requires its separate exact authorization phrase"
        )
    if not 1 <= len(variants) <= 2 or any(
        value not in {"baseline", "thinking_off"} for value in variants
    ):
        raise ValueError("end-to-end accepts one or two approved variants")
    cases = _load_manifest()
    selected = [
        _case_by_id(cases, case_id) for case_id in FIXED_REQUEST_CASES
    ]
    with snapshot_application() as application:
        api_key = load_api_key(application.config.api_key_ref)
        rows = []
        for variant_name in variants:
            variant = next(
                value for value in LIVE_VARIANTS if value.name == variant_name
            )
            grounded_provider = _live_provider(application, variant, api_key)

            def provider_factory(role: str) -> object:
                if role == "grounded_answer":
                    return grounded_provider
                return application.provider(role)

            service = application.ask_service
            service.query_analyzer.provider_factory = provider_factory
            service.answer_service.provider_factory = provider_factory
            for case in selected:
                response = service.ask(
                    AskRequest(query=case["query"], mode="fast")
                )
                trace = service.get_trace(response.run_id) or {}
                rows.append(
                    {
                        "request_id": case["case_id"],
                        "variant": variant_name,
                        "status": response.status,
                        "termination_reason": response.termination_reason,
                        "answer_block_count": len(response.answer_blocks),
                        "citation_count": len(response.citations),
                        "latency_ms": response.trace_summary.latency_ms,
                        "query_analysis_retry_count": trace.get(
                            "query_analysis_retry_count"
                        ),
                        "answer_provider_call_count": trace.get(
                            "answer_provider_call_count"
                        ),
                        "repair_calls": trace.get("repair_calls"),
                        "provider_error_code": trace.get(
                            "provider_error_code"
                        ),
                    }
                )
    payload = {
        "h0_mode": "authorized_end_to_end",
        "runs": len(rows),
        "variants": list(variants),
        "rows": rows,
    }
    assert_bounded_output(payload)
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "V4.1 H0 bounded investigation. The default command is local and "
            "never loads an API key or calls a Provider."
        )
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("deterministic")
    live = subparsers.add_parser("live-replay")
    live.add_argument("--authorization", default="")
    live.add_argument(
        "--interactive-review",
        action="store_true",
        help=(
            "Review selected full Draft/Evidence in the current TTY; "
            "nothing is persisted."
        ),
    )
    live.add_argument(
        "--checkpoint",
        type=Path,
        default=DEFAULT_CHECKPOINT_PATH,
        help=(
            "Atomic bounded checkpoint path. The file never contains "
            "prompts, answer bodies, transcript Evidence, credentials, or "
            "raw Provider responses."
        ),
    )
    e2e = subparsers.add_parser("end-to-end")
    e2e.add_argument("--authorization", default="")
    e2e.add_argument(
        "--variant",
        action="append",
        choices=("baseline", "thinking_off"),
        dest="variants",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    command = args.command or "deterministic"
    if command == "deterministic":
        payload = deterministic_investigation()
    elif command == "live-replay":
        if args.authorization != LIVE_AUTHORIZATION_PHRASE:
            raise SystemExit(
                "live-replay requires the exact explicit-authorization phrase"
            )
        if not args.interactive_review:
            raise SystemExit(
                "live-replay requires --interactive-review before any "
                "Provider call"
            )
        if not sys.stdin.isatty():
            raise SystemExit(
                "live-replay interactive review requires a TTY"
            )
        tty_preflight = preflight_quality_review_tty()
        payload = run_live_replay(
            args.authorization,
            reviewer=terminal_quality_reviewer,
            tty_preflight=tty_preflight,
            checkpoint_path=args.checkpoint,
        )
    else:
        payload = run_end_to_end(
            args.authorization, tuple(args.variants or ())
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
