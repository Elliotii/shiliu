from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any

from pydantic import BaseModel

from shiliu.app import Application
from shiliu.ask.contracts import AskRequest
from shiliu.ask.deep.budget import DeepSearchBudget
from shiliu.ask.deep.service import DeepSearchService
from shiliu.ask.query_analysis import QueryAnalyzer
from shiliu.config import AppPaths, load_api_key, load_config
from shiliu.llm import OpenAICompatibleProvider
from shiliu.research.errors import ResearchUnsafeState
from shiliu.research.provider_wiring import (
    ProviderCallContext,
    ReceiptBoundProviderService,
)


AUTHORIZED_ENDPOINT = "https://api.deepseek.com/v1"
AUTHORIZED_MODEL = "deepseek-v4-pro"
MAX_TOTAL_LOGICAL_CALLS = 17
MAX_TOTAL_HTTP_ATTEMPTS = 34
MAX_WALL_SECONDS = 34 * 60


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    return value


def _write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(_jsonable(value), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


class _CappedProvider:
    def __init__(self, meter: _CaseMeter, provider: object) -> None:
        self.meter = meter
        self.provider = provider

    def generate_structured(self, **kwargs):
        if self.meter.logical_calls >= self.meter.logical_cap:
            raise ResearchUnsafeState(
                f"{self.meter.case_id} logical Provider call cap exhausted"
            )
        self.meter.logical_calls += 1
        return self.provider.generate_structured(**kwargs)  # type: ignore[attr-defined]


class _CaseMeter:
    def __init__(self, *, case_id: str, logical_cap: int, factory: object) -> None:
        self.case_id = case_id
        self.logical_cap = logical_cap
        self.factory = factory
        self.logical_calls = 0

    def __call__(self, role: str) -> _CappedProvider:
        provider = self.factory(role)  # type: ignore[operator]
        return _CappedProvider(self, provider)


def _paths(root: Path) -> AppPaths:
    return AppPaths(
        state_dir=root,
        content_dir=root / "artifacts",
        database=root / "eval.db",
        config=root / "eval.config.not-present.toml",
        logs_dir=root / "logs",
        videos_dir=root / "artifacts" / "videos",
        sync_lock=root / "eval.sync.lock",
    )


def _actual_provider_factory(*, api_key: str, config: object):
    def factory(role: str) -> OpenAICompatibleProvider:
        if role not in {"query_analysis", "agent_action", "grounded_answer"}:
            raise ResearchUnsafeState(f"unauthorized Gate B role: {role}")
        grounded = role == "grounded_answer"
        return OpenAICompatibleProvider(
            base_url=str(config.llm_base_url),
            api_key=api_key,
            model=str(config.model_for(role)),
            timeout_seconds=180,
            thinking_enabled=grounded,
            reasoning_effort="high" if grounded else None,
        )

    return factory


def _start_case(app: Application, case: dict[str, Any]) -> ProviderCallContext:
    case_id = str(case["case_id"])
    task_id = "rtask_gate_b_" + case_id.lower().replace("-", "_")
    app.research.create_task(
        command_id=f"gate-b:{case_id}:create",
        task_id=task_id,
        objective=str(case["objective"]),
        success_constraints=list(case["success_constraints"]),
        evidence_policy={
            "authority": "eval_snapshot_exact_replay",
            "gate_b_case": case_id,
        },
    )
    claim = app.research.claim_owner(
        task_id=task_id,
        command_id=f"gate-b:{case_id}:claim",
        owner_id="gate-b-eval-worker",
        expected_state_version=0,
        lease_seconds=int(case["wall_time_seconds"]) + 300,
    )
    attempt = app.research.start_attempt(
        task_id=task_id,
        command_id=f"gate-b:{case_id}:start",
        owner_id="gate-b-eval-worker",
        owner_epoch=int(claim["owner_epoch"]),
        expected_state_version=1,
    )
    return ProviderCallContext(
        task_id=task_id,
        attempt_id=str(attempt["attempt_id"]),
        owner_id="gate-b-eval-worker",
        owner_epoch=int(claim["owner_epoch"]),
        expected_state_version=2,
        expected_checkpoint_id=None,
        expected_control_generation=0,
        operation_key=f"gate-b:{case_id}",
    )


def _run_case(
    *,
    app: Application,
    case: dict[str, Any],
    provider_factory: object,
    root: Path,
) -> dict[str, Any]:
    case_id = str(case["case_id"])
    case_dir = root / "cases" / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        case_dir / "request.json",
        {
            "case_id": case_id,
            "objective": case["objective"],
            "success_constraints": case["success_constraints"],
            "expected_outcomes": case["expected_outcomes"],
        },
    )
    context = _start_case(app, case)
    wiring = ReceiptBoundProviderService(
        db=app.db,
        kernel=app.research,
        provider_dispatch_authorized=True,
    )
    bound = wiring.factory(context=context, provider_factory=provider_factory)
    meter = _CaseMeter(
        case_id=case_id,
        logical_cap=int(case["logical_call_cap"]),
        factory=bound,
    )
    started = time.monotonic()
    query_plan = QueryAnalyzer(meter).analyze(str(case["objective"]))
    if query_plan.error:
        raise ResearchUnsafeState(
            f"{case_id} query_analysis failed: {query_plan.error}"
        )
    budget = DeepSearchBudget(
        max_decision_rounds=int(case["agent_action_cap"]),
        max_tool_calls=int(case["research_action_cap"]),
        total_runtime_seconds=float(case["wall_time_seconds"]),
        search_phase_cutoff_seconds=float(case["search_time_seconds"]),
        final_answer_reserve_seconds=(
            float(case["wall_time_seconds"]) - float(case["search_time_seconds"])
        ),
    )
    deep = DeepSearchService(
        db=app.db,
        artifacts=app.artifacts,
        product_search=app.product_search,
        provider_factory=meter,
        runtime_corpus_identity=app.runtime_config.corpus_identity,
        budget=budget,
    )
    response, trace = deep.ask(
        AskRequest(query=str(case["objective"]), mode="deep")
    )
    raw_task = app.research.get_task(context.task_id)
    unresolved = [
        effect
        for effect in raw_task["side_effects"]
        if effect["status"] in {"reserved", "in_flight", "unknown"}
    ]
    if unresolved:
        raise ResearchUnsafeState(
            f"{case_id} has unresolved Provider SideEffect; stop without replay"
        )
    snapshot = wiring.budget_snapshot(context.task_id)
    elapsed = time.monotonic() - started
    if snapshot.transport_calls > int(case["http_attempt_cap"]):
        raise ResearchUnsafeState(f"{case_id} HTTP attempt cap exceeded")
    result = {
        "case_id": case_id,
        "evaluation_path": "receipt_bound_deep_ask_on_gate_a_eval_snapshot",
        "program_answer_status": (
            "valid_insufficient"
            if response.status == "insufficient"
            else "valid_partial"
        ),
        "outer_audit_status": "not_exercised_no_provider_evaluator_authority",
        "answer": response,
        "query_plan": query_plan,
        "elapsed_seconds": round(elapsed, 3),
        "logical_calls": meter.logical_calls,
        "budget_snapshot": snapshot,
        "task_id": context.task_id,
        "attempt_id": context.attempt_id,
    }
    _write_json(case_dir / "result.json", result)
    _write_json(case_dir / "trace_projection.json", trace)
    _write_json(
        case_dir / "evidence_citations.json",
        [citation.model_dump(mode="json") for citation in response.citations],
    )
    _write_json(case_dir / "research_task_trace.json", raw_task)
    with (case_dir / "usage_cost.jsonl").open("w", encoding="utf-8") as stream:
        for action in raw_task["inner_actions"]:
            if action["action_schema_version"] != "v5-a-gate-b-provider-call-v1":
                continue
            observation = action.get("observation", {})
            stream.write(
                json.dumps(
                    _jsonable(
                        {
                            "action_id": action["action_id"],
                            "role": observation.get("provider_call", {}).get("role"),
                            "request_hash": action["request_hash"],
                            "side_effect_id": action["side_effect_id"],
                            "provider_call": observation.get("provider_call"),
                            "status": action["status"],
                        }
                    ),
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.eval_root.expanduser().resolve()
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("entry_gate", {}).get("status") != "pass":
        raise ResearchUnsafeState("formal Gate B Entry Gate is not pass")
    if manifest.get("provider_calls_performed") != 0:
        raise ResearchUnsafeState("formal Gate B manifest is not at call count zero")
    run_started = time.monotonic()
    config = load_config(AppPaths.defaults())
    if config.llm_base_url.rstrip("/") != AUTHORIZED_ENDPOINT:
        raise ResearchUnsafeState("configured Provider endpoint is not authorized")
    for role in ("query_analysis", "agent_action", "grounded_answer"):
        if config.model_for(role) != AUTHORIZED_MODEL:
            raise ResearchUnsafeState(f"configured {role} model is not authorized")
    api_key = load_api_key(config.api_key_ref)
    manifest["credential_access"] = {
        "status": "success",
        "source": "existing_keychain_reference",
        "reference_sha256": hashlib.sha256(
            config.api_key_ref.encode("utf-8")
        ).hexdigest(),
        "accessed_at": _utc_now(),
    }
    _write_json(manifest_path, manifest)
    app = Application(_paths(root))
    actual_factory = _actual_provider_factory(api_key=api_key, config=config)
    del api_key
    results: list[dict[str, Any]] = []
    try:
        mandatory = [
            case for case in manifest["cases"] if case["case_id"] in {"GB-G-01", "GB-I-01"}
        ]
        for case in mandatory:
            results.append(
                _run_case(
                    app=app,
                    case=case,
                    provider_factory=actual_factory,
                    root=root,
                )
            )
        exercised_hitl = any(
            result["answer"].termination_reason == "needs_user_input"
            if hasattr(result["answer"], "termination_reason")
            else False
            for result in results
        )
        if not exercised_hitl:
            hitl = next(
                case for case in manifest["cases"] if case["case_id"] == "GB-H-01"
            )
            results.append(
                _run_case(
                    app=app,
                    case=hitl,
                    provider_factory=actual_factory,
                    root=root,
                )
            )
    except Exception as exc:
        manifest["run_status"] = "stopped_fail_closed"
        manifest["stop"] = {
            "exception_type": type(exc).__name__,
            "message": str(exc)[:500],
            "at": _utc_now(),
        }
        _write_json(manifest_path, manifest)
        raise
    total_logical = sum(int(result["logical_calls"]) for result in results)
    total_http = sum(
        int(result["budget_snapshot"].transport_calls) for result in results
    )
    total_cost = sum(
        Decimal(result["budget_snapshot"].committed_cost_usd)
        for result in results
    )
    elapsed = time.monotonic() - run_started
    if (
        total_logical > MAX_TOTAL_LOGICAL_CALLS
        or total_http > MAX_TOTAL_HTTP_ATTEMPTS
        or elapsed > MAX_WALL_SECONDS
        or total_cost > Decimal("0.50")
    ):
        raise ResearchUnsafeState("formal Gate B aggregate hard cap exceeded")
    manifest.update(
        {
            "run_status": "completed_pending_human_review",
            "run_completed_at": _utc_now(),
            "provider_calls_performed": total_logical,
            "http_attempts": total_http,
            "total_cost_usd": str(total_cost),
            "wall_time_seconds": round(elapsed, 3),
            "executed_cases": [result["case_id"] for result in results],
        }
    )
    _write_json(manifest_path, manifest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
