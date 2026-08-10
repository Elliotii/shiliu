from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from shiliu.app import Application
from shiliu.ask.deep.budget import DeepSearchBudget
from shiliu.ask.evidence import TranscriptEvidenceMaterializer
from shiliu.config import AppPaths, load_api_key, load_config
from shiliu.research.inner_service import InnerResearchService
from shiliu.research.product_service import (
    ResearchProductService,
    grounded_current_evidence_profile,
)
from shiliu.research.provider_product import (
    ReceiptBoundDeepResearchExecutor,
    ReceiptBoundResearchProductOrchestrator,
)
from shiliu.research.provider_wiring import (
    ProviderRunBudgetPolicy,
    ReceiptBoundProviderService,
)
from scripts.v5_a_gate_b_postfix_validate import (
    _actual_provider_factory,
    _case_projection,
    _settle_running_product_boundary,
    _usage_rows,
)
from scripts.v5_d_r1_treatment import (
    R1ExperimentalReceiptBoundDeepResearchExecutor,
)


WORKTREE = Path("/Users/elliot/.codex/worktrees/5eb4/Shiliu")
STAGE0_ROOT = Path(
    "/Users/elliot/.codex/private/Shiliu/V5-D/stage0-20260811-MAoyel"
)
OLD_R1_ROOT = Path(
    "/Users/elliot/.codex/private/Shiliu/V5-D/r1-20260811-frozen-A"
)
R1_ROOT = Path(
    "/Users/elliot/.codex/private/Shiliu/V5-D/r1-e1-20260811-frozen-A"
)
EXPERIMENT_ID = "V5D-R1-E1-SOURCE-GATE-001"
AUTHORIZED_ENDPOINT = "https://api.deepseek.com/v1"
AUTHORIZED_MODEL = "deepseek-v4-pro"
SOURCE_CASE_IDS = ("V5D-S0-D-02", "V5D-S0-D-04")
ARMS = ("baseline", "treatment")
FROZEN_SEQUENCE = (
    ("V5D-S0-D-02", "treatment"),
    ("V5D-S0-D-04", "treatment"),
    ("V5D-S0-D-04", "baseline"),
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def canonical(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest(value: object) -> str:
    data = (
        value
        if isinstance(value, bytes)
        else (
            value.encode("utf-8")
            if isinstance(value, str)
            else canonical(value).encode("utf-8")
        )
    )
    return hashlib.sha256(data).hexdigest()


def jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value):
        return jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, (Path, Decimal)):
        return str(value)
    return value


def write_private(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            jsonable(value), ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    path.chmod(0o600)


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=WORKTREE,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def paths(root: Path) -> AppPaths:
    return AppPaths(
        state_dir=root,
        content_dir=root / "artifacts",
        database=root / "eval.db",
        config=root / "eval.config.not-present.toml",
        logs_dir=root / "logs",
        videos_dir=root / "artifacts" / "videos",
        sync_lock=root / "eval.sync.lock",
    )


def task_id(case_id: str, arm: str, outer_attempt: int) -> str:
    identity = f"{EXPERIMENT_ID}|{case_id}|{arm}|A{outer_attempt}"
    return "rtask_" + digest(identity)[:32]


def all_task_ids() -> tuple[str, ...]:
    return tuple(
        task_id(case_id, arm, attempt)
        for case_id, arm in FROZEN_SEQUENCE
        for attempt in (1, 2)
    )


def task_identity_manifest() -> list[dict[str, Any]]:
    return [
        {
            "case_id": case_id,
            "arm": arm,
            "outer_attempt": attempt,
            "task_id_sha256": digest(task_id(case_id, arm, attempt)),
        }
        for case_id, arm in FROZEN_SEQUENCE
        for attempt in (1, 2)
    ]


def residual_budget_policy(started_at: str) -> ProviderRunBudgetPolicy:
    return ProviderRunBudgetPolicy(
        run_id=EXPERIMENT_ID,
        task_ids=all_task_ids(),
        max_logical_calls=99,
        max_http_attempts=203,
        max_input_tokens=1_051_107,
        max_output_tokens=139_451,
        max_wall_seconds=5_719,
        reserve_stop_usd=Decimal("0.159353387"),
        absolute_max_cost_usd=Decimal("0.199353387"),
        started_at=started_at,
    )


def corpus_snapshot(database: Path) -> dict[str, Any]:
    connection = sqlite3.connect(
        f"file:{database}?mode=ro&immutable=1", uri=True
    )
    connection.row_factory = sqlite3.Row
    try:
        schema = connection.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0]
        videos = connection.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        completed = connection.execute(
            "SELECT COUNT(*) FROM videos WHERE status='completed'"
        ).fetchone()[0]
        lexical = [
            list(row)
            for row in connection.execute(
                "SELECT index_name,index_version,eligible_video_count,"
                "video_unit_count,chunk_unit_count FROM retrieval_index_meta "
                "ORDER BY index_name"
            )
        ]
        dense = [
            list(row)
            for row in connection.execute(
                "SELECT index_name,dense_index_version,model_id,total_unit_count "
                "FROM retrieval_dense_index_meta ORDER BY index_name"
            )
        ]
        units = [
            tuple(row)
            for row in connection.execute(
                "SELECT unit_id,video_id,content_hash,index_version "
                "FROM retrieval_units ORDER BY unit_id"
            )
        ]
    finally:
        connection.close()
    return {
        "schema": int(schema),
        "videos": int(videos),
        "completed_videos": int(completed),
        "lexical_meta": lexical,
        "dense_meta": dense,
        "retrieval_unit_manifest_sha256": digest(units),
    }


def load_source_cases() -> list[dict[str, Any]]:
    path = STAGE0_ROOT / "custody/discovery_manifest.private.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = [
        case for case in payload["cases"] if case["case_id"] in SOURCE_CASE_IDS
    ]
    if tuple(sorted(case["case_id"] for case in cases)) != tuple(
        sorted(SOURCE_CASE_IDS)
    ):
        raise RuntimeError("R1 source case identity mismatch")
    for case in cases:
        if digest(case["body"]) != case["body_sha256"]:
            raise RuntimeError("R1 source case body hash mismatch")
    return cases


def validate_entry() -> dict[str, Any]:
    receipt_path = R1_ROOT / "freeze_receipt.private.json"
    if not receipt_path.is_file():
        raise RuntimeError("R1-E1 freeze receipt is missing")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("experiment_id") != EXPERIMENT_ID:
        raise RuntimeError("R1-E1 experiment identity mismatch")
    if git("branch", "--show-current") != "codex/v5-d":
        raise RuntimeError("R1-E1 branch identity mismatch")
    if git("rev-parse", "HEAD") != receipt["freeze_commit"]:
        raise RuntimeError("R1-E1 freeze commit mismatch")
    if git("status", "--porcelain"):
        raise RuntimeError("R1-E1 frozen worktree is not clean")
    manifest_path = (
        WORKTREE / "V5_D_CANDIDATE_REVISION_R1_E1_EXPERIMENT_FREEZE.json"
    )
    if digest(manifest_path.read_bytes()) != receipt["experiment_manifest_sha256"]:
        raise RuntimeError("R1-E1 experiment manifest drift")
    if corpus_snapshot(R1_ROOT / "isolated/eval.db") != receipt["corpus_snapshot"]:
        raise RuntimeError("R1-E1 corpus/index snapshot drift")
    artifact_manifest = R1_ROOT / "artifact_snapshot.sha256"
    if digest(artifact_manifest.read_bytes()) != receipt[
        "artifact_snapshot_manifest_sha256"
    ]:
        raise RuntimeError("R1-E1 artifact snapshot manifest drift")
    provenance = receipt["carried_forward_provenance"]
    historical_paths = {
        "old_private_freeze_receipt_sha256": OLD_R1_ROOT
        / "freeze_receipt.private.json",
        "old_private_run_manifest_sha256": OLD_R1_ROOT
        / "runs/run_manifest.private.json",
        "old_final_isolated_db_sha256": OLD_R1_ROOT / "isolated/eval.db",
        "old_invalid_d02_treatment_evidence_sha256": OLD_R1_ROOT
        / "runs/attempts/V5D-S0-D-02/treatment/A1/exception.private.json",
        "d02_baseline_deep_trace_sha256": OLD_R1_ROOT
        / "runs/attempts/V5D-S0-D-02/baseline/A1/deep_provider_trace.private.json",
    }
    for key, path in historical_paths.items():
        if digest(path.read_bytes()) != provenance[key]:
            raise RuntimeError(f"R1-E1 historical provenance drift: {key}")
    reserve_key = STAGE0_ROOT / "custody/reserve_key.sealed"
    reserve_ciphertext = STAGE0_ROOT / "custody/reserve_manifest.aes256.enc"
    if reserve_key.stat().st_mode & 0o777:
        raise RuntimeError("reserve key is not sealed")
    if digest(reserve_ciphertext.read_bytes()) != receipt[
        "reserve_ciphertext_sha256"
    ]:
        raise RuntimeError("reserve ciphertext drift")
    if sum(
        1
        for line in (STAGE0_ROOT / "custody/access_log.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ) != receipt["reserve_access_log_entries_at_freeze"]:
        raise RuntimeError("reserve access log changed after R1-E1 freeze")
    return receipt


class CapturingBaselineExecutor(ReceiptBoundDeepResearchExecutor):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.last_trace: dict[str, Any] | None = None

    def execute(self, **kwargs: Any):  # type: ignore[no-untyped-def]
        output = super().execute(**kwargs)
        self.last_trace = dict(output.trace)
        return output


def _run_manifest(receipt: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    path = R1_ROOT / "runs/run_manifest.private.json"
    if path.exists():
        return path, json.loads(path.read_text(encoding="utf-8"))
    return path, {
        "experiment_id": EXPERIMENT_ID,
        "freeze_commit": receipt["freeze_commit"],
        "freeze_receipt_sha256": digest(
            (R1_ROOT / "freeze_receipt.private.json").read_bytes()
        ),
        "started_at": now(),
        "status": "initialized",
        "credential_access": {
            "status": "not_yet_accessed",
            "value_recorded": False,
        },
        "attempts": [],
    }


def _validate_attempt_order(
    manifest: dict[str, Any], case_id: str, arm: str, outer_attempt: int
) -> None:
    attempts = manifest["attempts"]
    if any(
        value["case_id"] == case_id
        and value["arm"] == arm
        and value["outer_attempt"] == outer_attempt
        for value in attempts
    ):
        raise RuntimeError("R1-E1 arm attempt is already recorded")
    if len(attempts) >= 6:
        raise RuntimeError("R1-E1 residual outer-attempt cap reached")
    if outer_attempt == 2:
        first = next(
            (
                value
                for value in attempts
                if value["case_id"] == case_id
                and value["arm"] == arm
                and value["outer_attempt"] == 1
            ),
            None,
        )
        if first is None or first.get("invalid_classification") not in {
            "provider_invalid",
            "infrastructure_invalid",
            "evaluation_execution_invalid",
        }:
            raise RuntimeError("R1-E1 replacement lacks a legal frozen invalid A1")
        return
    completed_a1 = [
        (value["case_id"], value["arm"])
        for value in attempts
        if value["outer_attempt"] == 1
    ]
    expected_prefix = list(FROZEN_SEQUENCE[: len(completed_a1)])
    if completed_a1 != expected_prefix:
        raise RuntimeError("R1-E1 recorded A1 order drift")
    expected = FROZEN_SEQUENCE[len(completed_a1)]
    if (case_id, arm) != expected:
        raise RuntimeError(f"R1-E1 next frozen arm is {expected}")


def run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", choices=SOURCE_CASE_IDS, required=True)
    parser.add_argument("--arm", choices=ARMS, required=True)
    parser.add_argument("--outer-attempt", type=int, choices=(1, 2), default=1)
    arguments = parser.parse_args()

    receipt = validate_entry()
    cases = load_source_cases()
    case = next(value for value in cases if value["case_id"] == arguments.case_id)
    manifest_path, manifest = _run_manifest(receipt)
    _validate_attempt_order(
        manifest, arguments.case_id, arguments.arm, arguments.outer_attempt
    )

    policy = residual_budget_policy(manifest["started_at"])
    if manifest.get("run_budget_policy_hash") not in (None, policy.policy_hash):
        raise RuntimeError("R1-E1 residual run budget policy drift")
    manifest["run_budget_policy_hash"] = policy.policy_hash
    manifest["run_budget_policy"] = policy.manifest()
    manifest["task_identities"] = task_identity_manifest()
    write_private(manifest_path, manifest)

    config = load_config(AppPaths.defaults())
    if config.llm_base_url.rstrip("/") != AUTHORIZED_ENDPOINT:
        raise RuntimeError("Provider endpoint mismatch")
    for role in ("query_analysis", "agent_action", "grounded_answer"):
        if config.model_for(role) != AUTHORIZED_MODEL:
            raise RuntimeError(f"Provider model mismatch for {role}")

    app = Application(paths(R1_ROOT / "isolated"))
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
        runner_id="v5-d-r1-e1-frozen-worker",
    )
    wiring = ReceiptBoundProviderService(
        db=app.db,
        kernel=app.research,
        provider_dispatch_authorized=True,
    )

    for preregistered_case_id, preregistered_arm in FROZEN_SEQUENCE:
        preregistered_case = next(
            value for value in cases if value["case_id"] == preregistered_case_id
        )
        for preregistered_attempt in (1, 2):
            identifier = task_id(
                preregistered_case["case_id"],
                preregistered_arm,
                preregistered_attempt,
            )
            created = app.research.create_task(
                    command_id=(
                        f"v5d-r1-e1:{EXPERIMENT_ID}:"
                        f"{preregistered_case['case_id']}:"
                        f"{preregistered_arm}:A{preregistered_attempt}:create"
                    ),
                    task_id=identifier,
                    objective=preregistered_case["body"],
                    success_constraints=list(
                        preregistered_case["gold_required_aspects"]
                    ),
                    evidence_policy={
                        "authority": "live_current_exact_replay",
                        "product_execution": "receipt_bound_provider",
                        "constraint_profile": "grounded_current_evidence",
                        "experiment_id": EXPERIMENT_ID,
                        "phase": "r1_e1_source_gate",
                        "case_id": preregistered_case["case_id"],
                        "arm": preregistered_arm,
                        "outer_attempt": preregistered_attempt,
                        "case_body_sha256": preregistered_case["body_sha256"],
                        "source_boundary_hash": preregistered_case[
                            "answerability"
                        ]["source_boundary_hash"],
                        "provider_run_budget": policy.evidence_policy_binding(
                            case_id=(
                                f"{preregistered_case['case_id']}:"
                                f"{preregistered_arm}:A{preregistered_attempt}"
                            )
                        ),
                    },
                    _server_constraint_profile=grounded_current_evidence_profile(),
            )
            if created["task_id"] != identifier:
                raise RuntimeError("R1-E1 Task identity mismatch")

    identifier = task_id(
        arguments.case_id, arguments.arm, arguments.outer_attempt
    )
    before = wiring.run_budget_snapshot(policy)
    api_key = load_api_key(config.api_key_ref)
    provider_factory = _actual_provider_factory(api_key=api_key, config=config)
    del api_key
    manifest["credential_access"] = {
        "status": "success",
        "source": "existing_keychain_reference",
        "reference_sha256": digest(config.api_key_ref),
        "accessed_at": now(),
        "secret_persistence": "forbidden",
        "value_recorded": False,
    }
    write_private(manifest_path, manifest)

    treatment = arguments.arm == "treatment"
    budget = DeepSearchBudget(
        max_decision_rounds=7 if treatment else 6,
        max_tool_calls=13 if treatment else 12,
        total_runtime_seconds=360,
        search_phase_cutoff_seconds=150,
        final_answer_reserve_seconds=210,
    )
    executor_kwargs = {
        "db": app.db,
        "artifacts": app.artifacts,
        "product_search": app.product_search,
        "runtime_corpus_identity": app.runtime_config.corpus_identity,
        "budget": budget,
    }
    if treatment:
        executor: Any = R1ExperimentalReceiptBoundDeepResearchExecutor(
            candidate_path=(
                WORKTREE
                / "V5_D_CANDIDATE_EVIDENCE_DELTA_FOLLOWUP_V1_1.json"
            ),
            source_index_runtime_health_valid=True,
            **executor_kwargs,
        )
    else:
        executor = CapturingBaselineExecutor(**executor_kwargs)
    orchestrator = ReceiptBoundResearchProductOrchestrator(
        db=app.db,
        kernel=app.research,
        inner=inner,
        product=product,
        receipt_service=wiring,
        provider_factory=provider_factory,
        deep_executor=executor,
        materializer=materializer,
        provider_product_authorized=True,
    )

    started = datetime.now(timezone.utc)
    deadline = started + timedelta(seconds=720)
    record = {
        "case_id": arguments.case_id,
        "case_body_sha256": case["body_sha256"],
        "arm": arguments.arm,
        "outer_attempt": arguments.outer_attempt,
        "task_id_sha256": digest(identifier),
        "frozen_sequence_ordinal": FROZEN_SEQUENCE.index(
            (arguments.case_id, arguments.arm)
        )
        + 1,
        "started_at": started.isoformat(timespec="microseconds"),
        "status": "running",
    }
    manifest["attempts"].append(record)
    manifest["status"] = "running"
    write_private(manifest_path, manifest)
    attempt_dir = (
        R1_ROOT
        / "runs/attempts"
        / arguments.case_id
        / arguments.arm
        / f"A{arguments.outer_attempt}"
    )
    attempt_dir.mkdir(parents=True, exist_ok=True)
    started_clock = time.monotonic()
    try:
        result = orchestrator.run_to_boundary(
            identifier,
            command_id=(
                f"v5d-r1-e1:{arguments.case_id}:{arguments.arm}:"
                f"A{arguments.outer_attempt}:provider-product-once"
            ),
            max_continuation_cycles=1,
            max_logical_calls=15 if treatment else 12,
            max_http_attempts=30 if treatment else 24,
            max_input_tokens=140_000 if treatment else 125_000,
            max_output_tokens=25_000 if treatment else 15_000,
            max_wall_time_seconds=720,
            case_deadline_at=deadline.isoformat(timespec="microseconds"),
            run_budget=policy,
        )
        result = _settle_running_product_boundary(
            product=product,
            task_id=identifier,
            command_id=(
                f"v5d-r1-e1:{arguments.case_id}:{arguments.arm}:"
                f"A{arguments.outer_attempt}:completion"
            ),
            current_result=result,
        )
        raw = app.research.get_task(identifier)
        control = app.research_control.get_status(identifier)
        projection = _case_projection(
            raw=raw, control=control, result=result, hitl=None
        )
        write_private(
            attempt_dir / "durable_product_projection.private.json", projection
        )
        write_private(attempt_dir / "research_task_trace.private.json", raw)
        if executor.last_trace is not None:
            write_private(
                attempt_dir / "deep_provider_trace.private.json",
                executor.last_trace,
            )
        usage = _usage_rows(raw)
        usage_path = attempt_dir / "usage_cost.private.jsonl"
        usage_path.write_text(
            "".join(canonical(value) + "\n" for value in usage),
            encoding="utf-8",
        )
        os.chmod(usage_path, 0o600)
        after = wiring.run_budget_snapshot(policy)
        record.update(
            {
                "status": "completed",
                "completed_at": now(),
                "elapsed_seconds": round(time.monotonic() - started_clock, 3),
                "task_status": projection["task_status"],
                "trace_count": projection["trace_count"],
                "evidence_use_count": projection["evidence_use_count"],
                "provider_receipt_count": len(usage),
                "attempt_count": projection["attempt_count"],
                "checkpoint_count": projection["checkpoint_count"],
                "budget_before": jsonable(before),
                "budget_after": jsonable(after),
                "deep_trace_sha256": (
                    digest(
                        (attempt_dir / "deep_provider_trace.private.json").read_bytes()
                    )
                    if (attempt_dir / "deep_provider_trace.private.json").is_file()
                    else None
                ),
            }
        )
    except Exception as exc:
        record.update(
            {
                "status": "exception",
                "completed_at": now(),
                "elapsed_seconds": round(time.monotonic() - started_clock, 3),
                "exception_type": type(exc).__name__,
                "exception_message": str(exc)[:1000],
                "exception_code": getattr(exc, "code", None),
            }
        )
        try:
            raw = app.research.get_task(identifier)
            write_private(attempt_dir / "research_task_trace.private.json", raw)
            usage = _usage_rows(raw)
            usage_path = attempt_dir / "usage_cost.private.jsonl"
            usage_path.write_text(
                "".join(canonical(value) + "\n" for value in usage),
                encoding="utf-8",
            )
            os.chmod(usage_path, 0o600)
            if executor.last_trace is not None:
                write_private(
                    attempt_dir / "deep_provider_trace.private.json",
                    executor.last_trace,
                )
            record["provider_receipt_count"] = len(usage)
            record["budget_after"] = jsonable(
                wiring.run_budget_snapshot(policy)
            )
        except Exception as capture_error:
            record["trace_capture_error"] = (
                f"{type(capture_error).__name__}: {capture_error}"[:500]
            )
        write_private(attempt_dir / "exception.private.json", record)
    manifest["budget_snapshot"] = jsonable(wiring.run_budget_snapshot(policy))
    manifest["status"] = "arm_attempt_complete"
    manifest["updated_at"] = now()
    write_private(manifest_path, manifest)
    print(
        json.dumps(
            {
                "experiment_id": EXPERIMENT_ID,
                "case_id": arguments.case_id,
                "arm": arguments.arm,
                "outer_attempt": arguments.outer_attempt,
                "status": record["status"],
                "task_id_sha256": record["task_id_sha256"],
                "provider_receipt_count": record.get("provider_receipt_count", 0),
                "budget_snapshot": manifest["budget_snapshot"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    run()
