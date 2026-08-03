from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any

from pydantic import BaseModel

from shiliu.app import Application
from shiliu.ask.deep.budget import DeepSearchBudget
from shiliu.ask.evidence import TranscriptEvidenceMaterializer
from shiliu.config import AppPaths, load_api_key, load_config
from shiliu.llm import OpenAICompatibleProvider
from shiliu.research.control_contracts import HumanDecisionRequest
from shiliu.research.errors import ResearchUnsafeState
from shiliu.research.inner_service import InnerResearchService
from shiliu.research.product_contracts import (
    CreateProductResearchRequest,
    RunProductResearchRequest,
)
from shiliu.research.product_service import ResearchProductService
from shiliu.research.provider_product import (
    ReceiptBoundDeepResearchExecutor,
    ReceiptBoundResearchProductOrchestrator,
)
from shiliu.research.provider_wiring import (
    ProviderRunBudgetPolicy,
    ReceiptBoundProviderService,
)


AUTHORIZED_ENDPOINT = "https://api.deepseek.com/v1"
AUTHORIZED_MODEL = "deepseek-v4-pro"
FULL_AUTHORIZED_CASES = ("GB-G-01", "GB-I-01", "GB-H-01")
REMAINING_AUTHORIZED_CASES = ("GB-I-01", "GB-H-01")
H_ONLY_AUTHORIZED_CASES = ("GB-H-01",)
COMPLETION_AUTHORIZED_CASES = ("GB-PC-G-01", "GB-PC-H-01")
ACCEPTED_PRODUCT_COMPLETION_HEAD = (
    "8d600b64338ca994a7ffc1f912365436969737df"
)
PARENT_G_MANIFEST_SHA256 = "24fa028dfa2af38d94f264ce4f97845063fe99c48233ffdd084520e7ce438075"
PARENT_G_EVAL_DB_SHA256 = "bb1965af04fac1e19d58aed088e4cfd15e5b2a5a34df30353e7cd63ee4745fdd"
PARENT_IH_MANIFEST_SHA256 = "12ec0b704f5f935a2048f5cfd64c7391c52345611a428683725eb93dcd8dae87"
PARENT_IH_EVAL_DB_SHA256 = "8271a5fdb074d02f45febf17cd409e019a598389463b6e3f174200caf0efbb7b"


def _run_envelope(
    *,
    remaining_ih: bool = False,
    h_only: bool = False,
    completion: bool = False,
) -> dict[str, Any]:
    if sum((remaining_ih, h_only, completion)) > 1:
        raise ResearchUnsafeState("remaining-I/H and H-only modes are mutually exclusive")
    if completion:
        return {
            "authorized_cases": COMPLETION_AUTHORIZED_CASES,
            "max_logical_calls": 10,
            "max_http_attempts": 20,
            "max_input_tokens": 80_000,
            "max_output_tokens": 17_792,
            "max_wall_seconds": 22 * 60,
            "reserve_stop_usd": Decimal("0.20"),
            "absolute_max_cost_usd": Decimal("0.25"),
        }
    if h_only:
        return {
            "authorized_cases": H_ONLY_AUTHORIZED_CASES,
            "max_logical_calls": 5,
            "max_http_attempts": 10,
            "max_input_tokens": 40_000,
            "max_output_tokens": 8_896,
            "max_wall_seconds": 12 * 60,
            "reserve_stop_usd": Decimal("0.398358803"),
            "absolute_max_cost_usd": Decimal("0.498358803"),
        }
    if remaining_ih:
        return {
            "authorized_cases": REMAINING_AUTHORIZED_CASES,
            "max_logical_calls": 10,
            "max_http_attempts": 20,
            "max_input_tokens": 80_000,
            "max_output_tokens": 17_792,
            "max_wall_seconds": 22 * 60,
            "reserve_stop_usd": Decimal("0.399023773"),
            "absolute_max_cost_usd": Decimal("0.499023773"),
        }
    return {
        "authorized_cases": FULL_AUTHORIZED_CASES,
        "max_logical_calls": 17,
        "max_http_attempts": 34,
        "max_input_tokens": 140_000,
        "max_output_tokens": 31_984,
        "max_wall_seconds": 34 * 60,
        "reserve_stop_usd": Decimal("0.40"),
        "absolute_max_cost_usd": Decimal("0.50"),
    }


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


def _task_id(run_id: str, case_id: str) -> str:
    identity = hashlib.sha256(f"{run_id}:{case_id}".encode()).hexdigest()[:24]
    return f"rtask_gate_b_postfix_{identity}"


def _completion_create_command(run_id: str, case_id: str) -> str:
    return f"completion:{run_id}:{case_id}:create"


def _completion_task_id(run_id: str, case_id: str) -> str:
    command_id = _completion_create_command(run_id, case_id)
    return f"rtask_{hashlib.sha256(command_id.encode()).hexdigest()[:32]}"


def _usage_rows(raw: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for action in raw["inner_actions"]:
        if action["action_schema_version"] != "v5-a-gate-b-provider-call-v1":
            continue
        call = action.get("observation", {}).get("provider_call", {})
        rows.append(
            {
                "action_id": action["action_id"],
                "attempt_id": action["attempt_id"],
                "role": call.get("role"),
                "provider_identity": call.get("provider_identity"),
                "request_hash": action["request_hash"],
                "side_effect_id": action["side_effect_id"],
                "provider_operation_id": call.get("provider_operation_id"),
                "receipt_hash": call.get("receipt_hash"),
                "result_reference": call.get("result_reference"),
                "usage": call.get("usage"),
                "cost_usd": call.get("cost_usd"),
                "transport_attempts": call.get("transport_attempts"),
                "status": action["status"],
            }
        )
    return rows


def _case_projection(
    *,
    raw: dict[str, Any],
    control: dict[str, Any],
    result: dict[str, Any],
    hitl: dict[str, Any] | None,
) -> dict[str, Any]:
    task = raw["task"]
    if task["status"] == "running":
        raise ResearchUnsafeState("post-fix product Task was left running")
    latest_artifact = raw["provisional_artifacts"][-1] if raw["provisional_artifacts"] else None
    latest_audit = raw["outer_audits"][-1] if raw["outer_audits"] else None
    terminal_result = raw["results"][-1] if raw["results"] else None
    open_inputs = list(control["open_input_requests"])
    return {
        "orchestration_result": result,
        "task_status": task["status"],
        "state_version": task["state_version"],
        "control_generation": task["control_generation"],
        "active_goal_id": task["active_goal_id"],
        "attempt_count": len(raw["attempts"]),
        "checkpoint_count": len(raw["checkpoints"]),
        "provisional_artifact": latest_artifact,
        "outer_audit": latest_audit,
        "terminal_result": terminal_result,
        "open_input_requests": open_inputs,
        "input_request_count": len(control["input_requests"]),
        "human_decision_count": len(control["human_decisions"]),
        "evidence_use_count": len(raw["evidence_uses"]),
        "current_evidence_use_ids": [
            value["evidence_use_id"] for value in raw["evidence_uses"]
        ],
        "trace_count": len(raw["traces"]),
        "provider_receipts": _usage_rows(raw),
        "hitl": hitl,
    }


def _load_case_projection(
    *,
    app: Application,
    task_id: str,
    result: dict[str, Any],
    hitl: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = app.research.get_task(task_id)
    control = app.research_control.get_status(task_id)
    return (
        _case_projection(raw=raw, control=control, result=result, hitl=hitl),
        raw,
    )


def _write_case_evidence(
    *, root: Path, case: dict[str, Any], projection: dict[str, Any], raw: dict[str, Any]
) -> None:
    case_dir = root / "cases" / str(case["case_id"])
    case_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        case_dir / "request.json",
        {
            "case_id": case["case_id"],
            "objective": case["objective"],
            "success_constraints": case["success_constraints"],
            "fixed_user_answer": case.get("fixed_user_answer"),
            "fixed_human_response": case.get("fixed_human_response"),
            "constraint_profile": case.get("constraint_profile"),
        },
    )
    _write_json(case_dir / "durable_product_projection.json", projection)
    _write_json(case_dir / "research_task_trace.json", raw)
    with (case_dir / "usage_cost.jsonl").open("w", encoding="utf-8") as stream:
        for row in projection["provider_receipts"]:
            stream.write(
                json.dumps(_jsonable(row), ensure_ascii=False, sort_keys=True) + "\n"
            )


def _prepare_hitl(
    *, app: Application, product: ResearchProductService, task_id: str, case: dict[str, Any]
) -> dict[str, Any]:
    pre = product.run_to_boundary(
        task_id,
        RunProductResearchRequest(
            command_id=f"postfix:{case['case_id']}:pre-hitl",
            max_steps=24,
        ),
    )
    status = app.research_control.get_status(task_id)
    open_inputs = status["open_input_requests"]
    if status["task"]["status"] != "waiting_user" or len(open_inputs) != 1:
        raise ResearchUnsafeState(
            "GB-H-01 did not form exactly one current InputRequest before Provider"
        )
    current = open_inputs[0]
    task = status["task"]
    fixed_response = case.get("fixed_human_response")
    fixed_answer = str(case.get("fixed_user_answer") or "")
    if fixed_response is not None:
        if not isinstance(fixed_response, dict):
            raise ResearchUnsafeState("fixed HumanDecision response is invalid")
        clarified_objective = str(fixed_response["objective"])
        clarified_constraints = list(fixed_response["success_constraints"])
    else:
        clarified_objective = f"{case['objective']}\n用户澄清：{fixed_answer}"
        clarified_constraints = list(case["success_constraints"])
    decision_request = HumanDecisionRequest(
        command_id=f"postfix:{case['case_id']}:fixed-answer",
        input_request_id=str(current["input_request_id"]),
        expected_state_version=int(task["state_version"]),
        expected_control_generation=int(task["control_generation"]),
        decision_kind="clarify_goal",
        response={
            "objective": clarified_objective,
            "success_constraints": clarified_constraints,
            "evidence_policy": {
                "authority": "server_registry_only",
                "user_clarification": fixed_answer,
            },
        },
    )
    decision = app.research_control.decide_input(
        task_id, decision_request, principal_id="local_operator"
    )
    replay = app.research_control.decide_input(
        task_id, decision_request, principal_id="local_operator"
    )
    if not replay.get("deduplicated") or replay.get("decision_id") != decision.get(
        "decision_id"
    ):
        raise ResearchUnsafeState("GB-H-01 HumanDecision was not exact-once")
    raw_after = app.research.get_task(task_id)
    child = raw_after["attempts"][-1]
    if (
        child["cause"] != "goal_revision"
        or child["parent_attempt_id"] != current["attempt_id"]
        or child["source_checkpoint_id"] != current["source_checkpoint_id"]
        or child["status"] != "running"
    ):
        raise ResearchUnsafeState("GB-H-01 HumanDecision lineage mismatch")
    return {
        "pre_provider_boundary": pre,
        "input_request_id": current["input_request_id"],
        "input_attempt_id": current["attempt_id"],
        "input_source_checkpoint_id": current["source_checkpoint_id"],
        "input_control_generation": int(task["control_generation"]),
        "fixed_user_answer": fixed_answer,
        "decision": decision,
        "decision_control_generation": int(decision["control_generation"]),
        "child_attempt_id": child["attempt_id"],
        "child_parent_attempt_id": child["parent_attempt_id"],
        "child_source_checkpoint_id": child["source_checkpoint_id"],
        "decision_replay_deduplicated": True,
    }


def _validate_entry(
    manifest: dict[str, Any],
    root: Path,
    *,
    remaining_ih: bool,
    h_only: bool,
    completion: bool,
    envelope: dict[str, Any],
) -> None:
    entry = manifest.get("entry_gate", {})
    if entry.get("status") != "pass":
        raise ResearchUnsafeState("post-fix Entry Gate is not pass")
    if manifest.get("provider_calls_performed") != 0:
        raise ResearchUnsafeState("post-fix manifest is not at call count zero")
    if manifest.get("formal_evaluation_root") != str(root):
        raise ResearchUnsafeState("post-fix manifest root identity mismatch")
    observed = tuple(str(case["case_id"]) for case in manifest.get("cases", []))
    if observed != envelope["authorized_cases"]:
        raise ResearchUnsafeState("post-fix exact case set/order is not authorized")
    limits = manifest.get("hard_limits", {})
    expected = {
        "max_logical_calls_total": envelope["max_logical_calls"],
        "max_http_attempts_total": envelope["max_http_attempts"],
        "max_input_tokens_total": envelope["max_input_tokens"],
        "max_output_tokens_total": envelope["max_output_tokens"],
        "max_wall_time_seconds_total": envelope["max_wall_seconds"],
        "reserve_stop_usd": str(envelope["reserve_stop_usd"]),
        "absolute_max_cost_usd_total": str(envelope["absolute_max_cost_usd"]),
    }
    if any(limits.get(key) != value for key, value in expected.items()):
        raise ResearchUnsafeState("post-fix run-wide manifest limits mismatch")
    if completion:
        if manifest.get("accepted_product_completion_head") != (
            ACCEPTED_PRODUCT_COMPLETION_HEAD
        ):
            raise ResearchUnsafeState("accepted product-completion HEAD mismatch")
        if manifest.get("case_manifest", {}).get("canonical_case_hashes") is None:
            raise ResearchUnsafeState("completion exact case hashes are not frozen")
    if remaining_ih or h_only:
        parent = manifest.get("parent_g_evidence", {})
        if (
            parent.get("manifest_sha256") != PARENT_G_MANIFEST_SHA256
            or parent.get("eval_db_sha256") != PARENT_G_EVAL_DB_SHA256
            or parent.get("provider_calls") != 5
            or parent.get("cost_usd") != "0.000976227"
        ):
            raise ResearchUnsafeState("frozen GB-G-01 parent evidence mismatch")
    if h_only:
        parent_ih = manifest.get("parent_ih_evidence", {})
        if (
            parent_ih.get("manifest_sha256") != PARENT_IH_MANIFEST_SHA256
            or parent_ih.get("eval_db_sha256") != PARENT_IH_EVAL_DB_SHA256
            or parent_ih.get("provider_calls") != 4
            or parent_ih.get("cost_usd") != "0.000664970"
            or parent_ih.get("H_provider_calls") != 0
        ):
            raise ResearchUnsafeState("frozen I/H recovery parent evidence mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-root", type=Path, required=True)
    parser.add_argument("--remaining-ih", action="store_true")
    parser.add_argument("--h-only", action="store_true")
    parser.add_argument("--completion", action="store_true")
    args = parser.parse_args()
    root = args.eval_root.expanduser().resolve()
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    envelope = _run_envelope(
        remaining_ih=args.remaining_ih,
        h_only=args.h_only,
        completion=args.completion,
    )
    authorized_cases = envelope["authorized_cases"]
    _validate_entry(
        manifest,
        root,
        remaining_ih=args.remaining_ih,
        h_only=args.h_only,
        completion=args.completion,
        envelope=envelope,
    )

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
        "secret_persistence": "forbidden",
    }
    _write_json(manifest_path, manifest)
    actual_factory = _actual_provider_factory(api_key=api_key, config=config)
    del api_key

    run_started_at = _utc_now()
    manifest["run_started_at"] = run_started_at
    task_ids = tuple(
        (
            _completion_task_id(str(manifest["run_id"]), case_id)
            if args.completion
            else _task_id(str(manifest["run_id"]), case_id)
        )
        for case_id in authorized_cases
    )
    run_policy = ProviderRunBudgetPolicy(
        run_id=str(manifest["run_id"]),
        task_ids=task_ids,
        started_at=run_started_at,
        max_logical_calls=envelope["max_logical_calls"],
        max_http_attempts=envelope["max_http_attempts"],
        max_input_tokens=envelope["max_input_tokens"],
        max_output_tokens=envelope["max_output_tokens"],
        max_wall_seconds=envelope["max_wall_seconds"],
        reserve_stop_usd=envelope["reserve_stop_usd"],
        absolute_max_cost_usd=envelope["absolute_max_cost_usd"],
    )
    manifest["run_budget_policy"] = run_policy.manifest()
    manifest["run_budget_policy_hash"] = run_policy.policy_hash
    _write_json(manifest_path, manifest)

    app = Application(_paths(root))
    materializer = TranscriptEvidenceMaterializer(app.db)
    inner = InnerResearchService(
        db=app.db,
        kernel=app.research,
        tools=app.research_inner.tools,
        materializer=materializer,
        provider_runs_authorized=True,
    )
    product = ResearchProductService(
        db=app.db,
        kernel=app.research,
        inner=inner,
        outer=app.research_outer,
        control=app.research_control,
        runner_id="gate-b-postfix-worker",
    )
    wiring = ReceiptBoundProviderService(
        db=app.db,
        kernel=app.research,
        provider_dispatch_authorized=True,
    )

    cases = {str(case["case_id"]): case for case in manifest["cases"]}
    for case_id, task_id in zip(authorized_cases, task_ids, strict=True):
        case = cases[case_id]
        if args.completion:
            created = product.create_task(
                CreateProductResearchRequest(
                    command_id=_completion_create_command(
                        str(manifest["run_id"]), case_id
                    ),
                    objective=str(case["objective"]),
                    success_constraints=list(case["success_constraints"]),
                    constraint_profile="grounded_current_evidence",
                    run_immediately=False,
                )
            )
            if created["task_id"] != task_id:
                raise ResearchUnsafeState("completion product Task identity mismatch")
        else:
            app.research.create_task(
                command_id=f"postfix:{case_id}:create",
                task_id=task_id,
                objective=str(case["objective"]),
                success_constraints=list(case["success_constraints"]),
                evidence_policy={
                    "authority": "eval_snapshot_exact_replay",
                    "gate_b_case": case_id,
                    "provider_run_budget": run_policy.evidence_policy_binding(
                        case_id=case_id
                    ),
                },
            )

    run_started_monotonic = time.monotonic()
    results: dict[str, Any] = {}
    try:
        for case_id in authorized_cases:
            case = cases[case_id]
            task_id = task_ids[authorized_cases.index(case_id)]
            case_started = datetime.now(timezone.utc)
            case_deadline = case_started + timedelta(
                seconds=int(case["wall_time_seconds"])
            )
            manifest.setdefault("case_runs", {})[case_id] = {
                "status": "started",
                "started_at": case_started.isoformat(timespec="microseconds"),
                "deadline_at": case_deadline.isoformat(timespec="microseconds"),
                "task_id": task_id,
            }
            _write_json(manifest_path, manifest)
            hitl = (
                _prepare_hitl(app=app, product=product, task_id=task_id, case=case)
                if case.get("fixed_human_response") is not None
                or case_id == "GB-H-01"
                else None
            )
            budget = DeepSearchBudget(
                max_decision_rounds=int(case["agent_action_cap"]),
                max_tool_calls=int(case["research_action_cap"]),
                total_runtime_seconds=float(case["wall_time_seconds"]),
                search_phase_cutoff_seconds=float(case["search_time_seconds"]),
                final_answer_reserve_seconds=(
                    float(case["wall_time_seconds"])
                    - float(case["search_time_seconds"])
                ),
            )
            orchestrator = ReceiptBoundResearchProductOrchestrator(
                db=app.db,
                kernel=app.research,
                inner=inner,
                product=product,
                receipt_service=wiring,
                provider_factory=actual_factory,
                deep_executor=ReceiptBoundDeepResearchExecutor(
                    db=app.db,
                    artifacts=app.artifacts,
                    product_search=app.product_search,
                    runtime_corpus_identity=app.runtime_config.corpus_identity,
                    budget=budget,
                ),
                materializer=materializer,
                provider_product_authorized=True,
            )
            result = orchestrator.run_to_boundary(
                task_id,
                command_id=f"postfix:{case_id}:provider-product-once",
                max_continuation_cycles=1,
                max_logical_calls=int(case["logical_call_cap"]),
                max_http_attempts=int(case["http_attempt_cap"]),
                max_input_tokens=int(case["input_token_cap"]),
                max_output_tokens=int(case["output_token_cap"]),
                max_wall_time_seconds=int(case["wall_time_seconds"]),
                case_deadline_at=case_deadline.isoformat(timespec="microseconds"),
                run_budget=run_policy,
            )
            projection, raw = _load_case_projection(
                app=app, task_id=task_id, result=result, hitl=hitl
            )
            _write_case_evidence(
                root=root, case=case, projection=projection, raw=raw
            )
            results[case_id] = projection
            if args.completion:
                if projection["task_status"] == "running":
                    raise ResearchUnsafeState("completion Task remained running")
                if not projection["provider_receipts"]:
                    raise ResearchUnsafeState("completion case has no Provider receipt")
                if not projection["outer_audit"]:
                    raise ResearchUnsafeState("completion case has no Outer audit")
                if case_id == "GB-PC-G-01" and (
                    projection["evidence_use_count"] < 1
                    or projection["task_status"] != "terminal"
                ):
                    raise ResearchUnsafeState(
                        "grounded completion case did not reach cited terminal boundary"
                    )
                if case_id == "GB-PC-H-01" and (
                    projection["input_request_count"] != 1
                    or projection["human_decision_count"] != 1
                    or projection["open_input_requests"]
                ):
                    raise ResearchUnsafeState(
                        "completion HITL case violated exact-one input lifecycle"
                    )
            manifest["case_runs"][case_id].update(
                {
                    "status": "completed_once",
                    "completed_at": _utc_now(),
                    "task_status": projection["task_status"],
                    "provider_receipts": len(projection["provider_receipts"]),
                }
            )
            manifest["run_budget_snapshot"] = wiring.run_budget_snapshot(run_policy)
            _write_json(manifest_path, manifest)
    except Exception as exc:
        manifest["run_status"] = "stopped_fail_closed_no_rerun"
        manifest["stop"] = {
            "exception_type": type(exc).__name__,
            "message": str(exc)[:500],
            "at": _utc_now(),
        }
        try:
            manifest["run_budget_snapshot"] = wiring.run_budget_snapshot(run_policy)
        except Exception as snapshot_exc:
            manifest["run_budget_snapshot_error"] = (
                f"{type(snapshot_exc).__name__}: {snapshot_exc}"
            )[:500]
        _write_json(manifest_path, manifest)
        raise

    aggregate = wiring.run_budget_snapshot(run_policy)
    elapsed = time.monotonic() - run_started_monotonic
    if (
        aggregate.committed_logical_calls > envelope["max_logical_calls"]
        or aggregate.committed_http_attempts > envelope["max_http_attempts"]
        or aggregate.committed_input_tokens > envelope["max_input_tokens"]
        or aggregate.committed_output_tokens > envelope["max_output_tokens"]
        or Decimal(aggregate.committed_cost_usd) > envelope["absolute_max_cost_usd"]
        or elapsed > envelope["max_wall_seconds"]
    ):
        raise ResearchUnsafeState("post-fix aggregate hard cap exceeded")
    manifest.update(
        {
            "run_status": "completed_once_pending_human_review",
            "run_completed_at": _utc_now(),
            "provider_calls_performed": aggregate.committed_logical_calls,
            "http_attempts": aggregate.committed_http_attempts,
            "input_tokens": aggregate.committed_input_tokens,
            "output_tokens": aggregate.committed_output_tokens,
            "total_cost_usd": aggregate.committed_cost_usd,
            "wall_time_seconds": round(elapsed, 3),
            "executed_cases": list(authorized_cases),
            "run_budget_snapshot": aggregate,
            "results": {
                case_id: {
                    "task_status": projection["task_status"],
                    "answer_status": (
                        projection["terminal_result"] or projection["provisional_artifact"] or {}
                    ).get("answer_status"),
                    "outer_audit_outcome": (
                        projection["outer_audit"] or {}
                    ).get("outcome"),
                    "open_input_requests": len(projection["open_input_requests"]),
                    "provider_receipts": len(projection["provider_receipts"]),
                }
                for case_id, projection in results.items()
            },
        }
    )
    _write_json(manifest_path, manifest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
