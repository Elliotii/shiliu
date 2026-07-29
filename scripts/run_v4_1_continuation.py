from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Iterable

from shiliu.ask import AskRequest, AskResponse

from run_v4_1_h0_investigation import (
    _atomic_write_checkpoint,
    _consume_tty_preflight,
    assert_checkpoint_bounded,
    preflight_quality_review_tty,
    snapshot_application,
    stable_hash,
)
from run_v4_goal3_eval import _deterministic_checks, _validate_citation


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPOSITORY_ROOT / "eval" / "v4_goal3_cases.json"
CHECKPOINT_VERSION = "v4.1-continuation-e2e-checkpoint-v1"
AUTHORIZATION_PHRASE = "V4_1_CONTINUATION_E2E_AUTHORIZED"
QUALITY_VALUES = {"pass", "partial", "fail"}
TOTAL_RUN_CAP = 12
TOTAL_LOGICAL_CAP = 56
TOTAL_HTTP_CAP = 112
CONSECUTIVE_PROVIDER_FAILURE_LIMIT = 2


@dataclass(frozen=True)
class PhaseSpec:
    phase_id: str
    mode: str
    code_state: str
    case_ids: tuple[str, ...]
    logical_cap: int
    http_cap: int
    logical_reservation_per_run: int
    http_reservation_per_run: int
    paired_before: str | None = None

    @property
    def checkpoint_path(self) -> Path:
        return (
            REPOSITORY_ROOT
            / ".h0"
            / f"v4_1_{self.phase_id}_e2e_checkpoint.json"
        )


PHASES = {
    "fast_before": PhaseSpec(
        "fast_before",
        "fast",
        "before_H1",
        (
            "no_evidence_quantum_protocol",
            "single_topic_context_compression",
            "cross_video_context_management",
            "partial_universal_claim",
        ),
        12,
        24,
        3,
        6,
    ),
    "fast_after": PhaseSpec(
        "fast_after",
        "fast",
        "after_H1",
        (
            "no_evidence_quantum_protocol",
            "single_topic_context_compression",
            "cross_video_context_management",
            "partial_universal_claim",
        ),
        12,
        24,
        3,
        6,
        paired_before="fast_before",
    ),
    "deep_before": PhaseSpec(
        "deep_before",
        "deep",
        "before_H2",
        ("contextual_tool_failure", "cross_video_context_management"),
        16,
        32,
        8,
        16,
    ),
    "deep_after": PhaseSpec(
        "deep_after",
        "deep",
        "after_H2",
        ("contextual_tool_failure", "cross_video_context_management"),
        16,
        32,
        8,
        16,
        paired_before="deep_before",
    ),
}


class E2ERecoveryBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class EphemeralRun:
    case_id: str
    public_measurement: dict[str, object]
    response: AskResponse
    full_current_evidence: tuple[dict[str, object], ...]
    private_strings: tuple[str, ...]

    @property
    def material_hash(self) -> str:
        return stable_hash(
            {
                "response": self.response.model_dump(mode="json"),
                "full_current_evidence": self.full_current_evidence,
            }
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _load_cases() -> dict[str, dict[str, Any]]:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {str(value["case_id"]): value for value in payload["cases"]}


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_code_digest(mode: str) -> str:
    shared = (
        "src/shiliu/ask/answer.py",
        "src/shiliu/ask/finalize.py",
        "src/shiliu/ask/validation.py",
        "src/shiliu/ask/contracts.py",
        "src/shiliu/ask/service.py",
    )
    deep = tuple(
        str(value.relative_to(REPOSITORY_ROOT))
        for value in sorted((REPOSITORY_ROOT / "src/shiliu/ask/deep").glob("*.py"))
    )
    names = shared + (deep if mode == "deep" else ())
    return stable_hash(
        [
            {
                "path": name,
                "sha256": _file_sha256(REPOSITORY_ROOT / name),
            }
            for name in names
        ]
    )


def campaign_identity(
    spec: PhaseSpec,
    *,
    query_hashes: dict[str, str],
    corpus_sha256: str,
    provider_identity: dict[str, object],
) -> dict[str, object]:
    value = {
        "checkpoint_version": CHECKPOINT_VERSION,
        "phase_id": spec.phase_id,
        "mode": spec.mode,
        "code_state": spec.code_state,
        "case_ids": list(spec.case_ids),
        "query_hashes": query_hashes,
        "manifest_sha256": _file_sha256(MANIFEST_PATH),
        "corpus_sha256": corpus_sha256,
        "source_code_sha256": source_code_digest(spec.mode),
        "provider_identity": provider_identity,
        "logical_cap": spec.logical_cap,
        "http_cap": spec.http_cap,
    }
    return {**value, "identity_sha256": stable_hash(value)}


def _new_checkpoint(
    spec: PhaseSpec, identity: dict[str, object]
) -> dict[str, object]:
    return {
        "checkpoint_version": CHECKPOINT_VERSION,
        "identity": identity,
        "state": "active",
        "created_at_utc": _utc_now(),
        "updated_at_utc": _utc_now(),
        "runs": {
            case_id: {"state": "pending"} for case_id in spec.case_ids
        },
        "completed_run_count": 0,
        "logical_provider_invocations": 0,
        "transport_http_attempts": 0,
        "consecutive_provider_failures": 0,
        "stop_reason": None,
    }


def _read_checkpoint(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise E2ERecoveryBlocked(f"invalid checkpoint object: {path.name}")
    return value


def _unsafe_states(value: dict[str, Any]) -> list[str]:
    result: list[str] = []
    runs = value.get("runs")
    if not isinstance(runs, dict):
        return ["malformed_runs"]
    for case_id, run in runs.items():
        state = run.get("state") if isinstance(run, dict) else "malformed"
        if state in {
            "in_flight",
            "provider_complete_pending_review",
            "review_in_progress",
        }:
            result.append(f"{case_id}:{state}")
    return result


def _all_checkpoint_totals(
    *, exclude: Path | None = None
) -> tuple[int, int, int]:
    runs = logical = http = 0
    for phase in PHASES.values():
        path = phase.checkpoint_path
        if exclude is not None and path == exclude:
            continue
        value = _read_checkpoint(path)
        if value is None:
            continue
        unsafe = _unsafe_states(value)
        if unsafe:
            raise E2ERecoveryBlocked(
                f"unknown in_flight state in {path.name}: {unsafe}"
            )
        runs += int(value.get("completed_run_count", 0))
        logical += int(value.get("logical_provider_invocations", 0))
        http += int(value.get("transport_http_attempts", 0))
    return runs, logical, http


class E2ECheckpointStore:
    def __init__(
        self,
        spec: PhaseSpec,
        identity: dict[str, object],
        *,
        private_strings: Iterable[str],
    ) -> None:
        self.spec = spec
        self.path = spec.checkpoint_path
        self.private_strings = tuple(private_strings)
        existing = _read_checkpoint(self.path)
        if existing is None:
            self.data = _new_checkpoint(spec, identity)
            self._write()
        else:
            self.data = existing
            if self.data.get("identity") != identity:
                raise E2ERecoveryBlocked(
                    "campaign identity mismatch; checkpoint cannot be mixed"
                )
            unsafe = _unsafe_states(self.data)
            if unsafe:
                raise E2ERecoveryBlocked(
                    f"unknown in_flight or private-loss state: {unsafe}"
                )

    def _write(self, extra_private: Iterable[str] = ()) -> None:
        self.data["updated_at_utc"] = _utc_now()
        assert_checkpoint_bounded(
            self.data,
            private_strings=(*self.private_strings, *tuple(extra_private)),
        )
        _atomic_write_checkpoint(self.path, self.data)

    def run(self, case_id: str) -> dict[str, Any]:
        runs = self.data["runs"]
        assert isinstance(runs, dict)
        value = runs[case_id]
        assert isinstance(value, dict)
        return value

    @property
    def terminal(self) -> bool:
        return self.data.get("state") in {"complete", "blocked"}

    def begin(self, case_id: str) -> None:
        run = self.run(case_id)
        if run.get("state") == "review_complete":
            return
        if run.get("state") != "pending":
            raise E2ERecoveryBlocked(
                f"run {case_id} cannot begin from {run.get('state')}"
            )
        phase_logical = int(self.data["logical_provider_invocations"])
        phase_http = int(self.data["transport_http_attempts"])
        if (
            phase_logical + self.spec.logical_reservation_per_run
            > self.spec.logical_cap
            or phase_http + self.spec.http_reservation_per_run
            > self.spec.http_cap
        ):
            raise E2ERecoveryBlocked("phase call cap is insufficient")
        other_runs, other_logical, other_http = _all_checkpoint_totals(
            exclude=self.path
        )
        if (
            other_runs + int(self.data["completed_run_count"]) + 1
            > TOTAL_RUN_CAP
            or other_logical
            + phase_logical
            + self.spec.logical_reservation_per_run
            > TOTAL_LOGICAL_CAP
            or other_http + phase_http + self.spec.http_reservation_per_run
            > TOTAL_HTTP_CAP
        ):
            raise E2ERecoveryBlocked("total continuation call cap is insufficient")
        run.clear()
        run.update(
            {
                "state": "in_flight",
                "wal_at_utc": _utc_now(),
                "logical_reservation": self.spec.logical_reservation_per_run,
                "http_reservation": self.spec.http_reservation_per_run,
            }
        )
        self._write()

    def checkpoint_provider_result(self, result: EphemeralRun) -> None:
        run = self.run(result.case_id)
        if run.get("state") != "in_flight":
            raise E2ERecoveryBlocked("Provider result has no matching WAL")
        logical = int(result.public_measurement["logical_provider_invocations"])
        http = int(result.public_measurement["transport_http_attempts"])
        if logical > int(run["logical_reservation"]):
            raise E2ERecoveryBlocked("logical invocation reservation exceeded")
        if http > int(run["http_reservation"]):
            raise E2ERecoveryBlocked("HTTP attempt reservation exceeded")
        run.clear()
        run.update(
            {
                "state": "provider_complete_pending_review",
                "provider_checkpointed_at_utc": _utc_now(),
                "measurement": result.public_measurement,
                "material_sha256": result.material_hash,
            }
        )
        self.data["logical_provider_invocations"] = (
            int(self.data["logical_provider_invocations"]) + logical
        )
        self.data["transport_http_attempts"] = (
            int(self.data["transport_http_attempts"]) + http
        )
        provider_failed = bool(
            result.public_measurement.get("provider_failed")
        )
        self.data["consecutive_provider_failures"] = (
            int(self.data["consecutive_provider_failures"]) + 1
            if provider_failed
            else 0
        )
        self._write(result.private_strings)

    def begin_review(self, result: EphemeralRun) -> None:
        run = self.run(result.case_id)
        if run.get("state") != "provider_complete_pending_review":
            raise E2ERecoveryBlocked("review has no checkpointed Provider result")
        if run.get("material_sha256") != result.material_hash:
            raise E2ERecoveryBlocked("review material identity mismatch")
        run["state"] = "review_in_progress"
        run["review_started_at_utc"] = _utc_now()
        self._write(result.private_strings)

    def finish_review(
        self,
        result: EphemeralRun,
        review: dict[str, str],
    ) -> None:
        run = self.run(result.case_id)
        if run.get("state") != "review_in_progress":
            raise E2ERecoveryBlocked("review completion state mismatch")
        scores = {
            name: review[name]
            for name in (
                "supportedness",
                "usefulness",
                "coverage",
                "status_honesty",
            )
        }
        if not set(scores.values()).issubset(QUALITY_VALUES):
            raise ValueError("quality score must be pass, partial, or fail")
        reason = " ".join(review["reason"].split())[:300]
        folded = reason.casefold()
        if any(
            value.strip() and value.strip().casefold() in folded
            for value in result.private_strings
        ):
            reason = "reason_redacted_private_overlap"
        run["state"] = "review_complete"
        run["review_completed_at_utc"] = _utc_now()
        run["quality_review"] = {
            **scores,
            "reason_summary": reason,
            "reason_sha256": stable_hash(review["reason"]),
            "material_sha256": result.material_hash,
        }
        self.data["completed_run_count"] = (
            int(self.data["completed_run_count"]) + 1
        )
        self._write(result.private_strings)

    def finish_phase(self) -> None:
        if all(
            self.run(case_id).get("state") == "review_complete"
            for case_id in self.spec.case_ids
        ):
            self.data["state"] = "complete"
            self.data["completed_at_utc"] = _utc_now()
        elif (
            int(self.data["consecutive_provider_failures"])
            >= CONSECUTIVE_PROVIDER_FAILURE_LIMIT
        ):
            self.data["state"] = "blocked"
            self.data["stop_reason"] = (
                "two_consecutive_provider_failures"
            )
        self._write()


def _provider_counts(mode: str, trace: dict[str, object]) -> tuple[int, int]:
    finalization = trace.get("finalization")
    finalization = finalization if isinstance(finalization, dict) else trace
    answer_calls = int(finalization.get("answer_provider_call_count", 0))
    answer_retries = int(finalization.get("transport_retry_count", 0))
    if mode == "fast":
        logical = 1 + answer_calls
        retries = int(trace.get("query_analysis_retry_count", 0)) + answer_retries
    else:
        rounds = int(trace.get("decision_rounds", 0))
        events = trace.get("events")
        decision_retries = sum(
            int(value.get("retry_count", 0))
            for value in (events if isinstance(events, list) else [])
            if isinstance(value, dict)
            and value.get("event_type") in {"decision", "decision_error"}
        )
        logical = rounds + answer_calls
        retries = decision_retries + answer_retries
    return logical, logical + retries


def _token_metrics(trace: dict[str, object]) -> dict[str, object]:
    usage_rows: list[dict[str, object]] = []
    value = trace.get("usage")
    if isinstance(value, list):
        usage_rows.extend(item for item in value if isinstance(item, dict))
    finalization = trace.get("finalization")
    if isinstance(finalization, dict):
        value = finalization.get("answer_usage")
        if isinstance(value, list):
            usage_rows.extend(item for item in value if isinstance(item, dict))
    prompt_tokens = sum(
        int(item.get("prompt_tokens", 0) or 0) for item in usage_rows
    )
    completion_tokens = sum(
        int(item.get("completion_tokens", 0) or 0) for item in usage_rows
    )
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "usage_row_count": len(usage_rows),
    }


def build_ephemeral_run(
    application: object,
    case_id: str,
    query: str,
    mode: str,
) -> EphemeralRun:
    response = application.ask_service.ask(  # type: ignore[attr-defined]
        AskRequest(query=query, mode=mode)
    )
    trace = application.ask_service.get_trace(response.run_id)  # type: ignore[attr-defined]
    if not isinstance(trace, dict):
        raise E2ERecoveryBlocked("product trace unavailable after Provider return")
    citation_checks: list[dict[str, object]] = []
    full_evidence: list[dict[str, object]] = []
    for citation in response.citations:
        _validate_citation(application, citation)  # type: ignore[arg-type]
        citation_checks.append(
            {"citation_id": citation.citation_id, "reconstructable": True}
        )
        full_evidence.append(
            {
                "citation_id": citation.citation_id,
                "title": citation.title,
                "start_time": citation.start_time,
                "end_time": citation.end_time,
                "quote_text": citation.quote_text,
                "source_version": citation.source_version,
            }
        )
    checks = _deterministic_checks(
        response,
        citation_checks=citation_checks,
        budget_respected=True,
    )
    if not all(checks.values()):
        raise E2ERecoveryBlocked(
            "deterministic response/citation validation failed: "
            f"{sorted(key for key, value in checks.items() if not value)}"
        )
    logical, http = _provider_counts(mode, trace)
    public = {
        "case_id": case_id,
        "mode": mode,
        "status": response.status,
        "termination_reason": response.termination_reason,
        "provider_failed": response.termination_reason == "provider_error",
        "latency_ms": response.trace_summary.latency_ms,
        "logical_provider_invocations": logical,
        "transport_http_attempts": http,
        "query_count": response.trace_summary.query_count,
        "retrieval_count": response.trace_summary.retrieval_count,
        "valid_evidence_count": response.trace_summary.valid_evidence_count,
        "context_span_count": response.trace_summary.context_span_count,
        "context_truncated": response.trace_summary.context_truncated,
        "repair_used": response.trace_summary.repair_used,
        "decision_rounds": response.trace_summary.decision_rounds,
        "tool_calls": response.trace_summary.tool_calls,
        "visited_video_count": response.trace_summary.visited_video_count,
        "visited_segment_count": response.trace_summary.visited_segment_count,
        "navigation_result_count": response.trace_summary.navigation_result_count,
        "citation_count": len(response.citations),
        "citation_ids": [value.citation_id for value in response.citations],
        "citation_validation": checks,
        "response_sha256": stable_hash(response.model_dump(mode="json")),
        **_token_metrics(trace),
    }
    private = (
        query,
        *tuple(block.text for block in response.answer_blocks),
        *tuple(response.limitations),
        *tuple(citation.quote_text for citation in response.citations),
    )
    return EphemeralRun(
        case_id=case_id,
        public_measurement=public,
        response=response,
        full_current_evidence=tuple(full_evidence),
        private_strings=tuple(value for value in private if value),
    )


def terminal_reviewer(run: EphemeralRun) -> dict[str, str]:
    if not sys.stdin.isatty():
        raise RuntimeError("quality review requires a real TTY")
    with (
        open("/dev/tty", "r", encoding="utf-8") as terminal_in,
        open("/dev/tty", "w", encoding="utf-8") as terminal_out,
    ):
        terminal_out.write(
            "\n=== V4.1 E2E EPHEMERAL QUALITY REVIEW ===\n"
            f"case_id: {run.case_id}\n"
            f"status: {run.response.status}\n"
            "ANSWER (not persisted):\n"
        )
        for block in run.response.answer_blocks:
            terminal_out.write(
                f"- {block.text}\n  citations: {block.citation_ids}\n"
            )
        terminal_out.write(f"limitations: {run.response.limitations}\n")
        terminal_out.write("CURRENT RECONSTRUCTED EVIDENCE (not persisted):\n")
        for value in run.full_current_evidence:
            terminal_out.write(
                f"[{value['citation_id']}] {value['title']} "
                f"{value['start_time']}-{value['end_time']}\n"
                f"{value['quote_text']}\n"
            )
        result: dict[str, str] = {}
        for name in (
            "supportedness",
            "usefulness",
            "coverage",
            "status_honesty",
        ):
            while True:
                terminal_out.write(f"{name} [pass/partial/fail]: ")
                terminal_out.flush()
                value = terminal_in.readline().strip().lower()
                if value in QUALITY_VALUES:
                    result[name] = value
                    break
        terminal_out.write("bounded reason (no copied private text): ")
        terminal_out.flush()
        result["reason"] = terminal_in.readline().strip()
        return result


def _provider_identity(application: object) -> dict[str, object]:
    config = application.config  # type: ignore[attr-defined]
    return {
        "base_url_sha256": stable_hash(str(config.llm_base_url)),
        "query_analysis_model": config.model_for("query_analysis"),
        "grounded_answer_model": config.model_for("grounded_answer"),
        "agent_action_model": config.model_for("agent_action"),
        "thinking": True,
        "reasoning_effort": "high",
        "configuration": "baseline_only",
    }


def run_phase(
    spec: PhaseSpec,
    *,
    application: object,
    corpus_sha256: str,
    reviewer: Callable[[EphemeralRun], dict[str, str]],
    event_hook: Callable[[str, str], None] | None = None,
) -> dict[str, object]:
    cases = _load_cases()
    query_hashes = {
        case_id: stable_hash(cases[case_id]["query"])
        for case_id in spec.case_ids
    }
    identity = campaign_identity(
        spec,
        query_hashes=query_hashes,
        corpus_sha256=corpus_sha256,
        provider_identity=_provider_identity(application),
    )
    if spec.paired_before:
        before = _read_checkpoint(PHASES[spec.paired_before].checkpoint_path)
        if before is None or before.get("state") != "complete":
            raise E2ERecoveryBlocked("paired Before phase is not complete")
        before_identity = before.get("identity")
        if (
            not isinstance(before_identity, dict)
            or before_identity.get("corpus_sha256") != corpus_sha256
            or before_identity.get("query_hashes") != query_hashes
        ):
            raise E2ERecoveryBlocked("paired corpus/query identity changed")
    store = E2ECheckpointStore(
        spec,
        identity,
        private_strings=(
            str(cases[case_id]["query"]) for case_id in spec.case_ids
        ),
    )
    if store.terminal:
        return store.data
    emit = event_hook or (lambda _event, _case_id: None)
    for case_id in spec.case_ids:
        if store.run(case_id).get("state") == "review_complete":
            continue
        store.begin(case_id)
        emit("provider_wal_persisted", case_id)
        run = build_ephemeral_run(
            application,
            case_id,
            str(cases[case_id]["query"]),
            spec.mode,
        )
        emit("provider_returned_before_checkpoint", case_id)
        store.checkpoint_provider_result(run)
        emit("provider_result_checkpointed", case_id)
        store.begin_review(run)
        emit("review_in_progress", case_id)
        review = reviewer(run)
        emit("review_returned_before_checkpoint", case_id)
        store.finish_review(run, review)
        emit("review_checkpointed", case_id)
        if (
            int(store.data["consecutive_provider_failures"])
            >= CONSECUTIVE_PROVIDER_FAILURE_LIMIT
        ):
            break
    store.finish_phase()
    return store.data


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Crash-safe bounded V4.1 continuation E2E runner."
    )
    parser.add_argument("--phase", required=True, choices=tuple(PHASES))
    parser.add_argument("--authorization", required=True)
    args = parser.parse_args()
    if args.authorization != AUTHORIZATION_PHRASE:
        raise PermissionError("exact continuation E2E authorization is required")
    proof = preflight_quality_review_tty()
    _consume_tty_preflight(proof)
    default_database = (
        Path.home() / ".local/share/shiliu/shiliu.db"
    )
    if not default_database.is_file():
        from shiliu.config import AppPaths

        default_database = AppPaths.defaults().database
    corpus_sha256 = _file_sha256(default_database)
    with snapshot_application() as application:
        payload = run_phase(
            PHASES[args.phase],
            application=application,
            corpus_sha256=corpus_sha256,
            reviewer=terminal_reviewer,
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("state") == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
