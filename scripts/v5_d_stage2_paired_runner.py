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
from scripts.v5_d_stage2_treatment import (
    ExperimentalReceiptBoundDeepResearchExecutor,
)


WORKTREE = Path("/Users/elliot/.codex/worktrees/5eb4/Shiliu")
STAGE0_ROOT = Path(
    "/Users/elliot/.codex/private/Shiliu/V5-D/stage0-20260811-MAoyel"
)
STAGE2_ROOT = Path(
    "/Users/elliot/.codex/private/Shiliu/V5-D/stage2-20260811-frozen-B"
)
EXPERIMENT_ID = "V5D-S2-PAIRED-EVAL-001"
AUTHORIZED_ENDPOINT = "https://api.deepseek.com/v1"
AUTHORIZED_MODEL = "deepseek-v4-pro"
SOURCE_CASE_IDS = ("V5D-S0-D-02", "V5D-S0-D-04")
RESERVE_CASE_IDS = (
    "V5D-S0-R-01",
    "V5D-S0-R-02",
    "V5D-S0-R-03",
    "V5D-S0-R-04",
)
ARMS = ("baseline", "treatment")


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


def task_ids_for_cases(case_ids: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        task_id(case_id, arm, attempt)
        for case_id in case_ids
        for arm in ARMS
        for attempt in (1, 2)
    )


def frozen_arm_order(case_id: str) -> tuple[str, str]:
    parity = int(digest(EXPERIMENT_ID + case_id), 16) % 2
    return ARMS if parity == 0 else tuple(reversed(ARMS))


def corpus_snapshot(database: Path) -> dict[str, Any]:
    connection = sqlite3.connect(
        f"file:{database}?mode=ro&immutable=1", uri=True
    )
    connection.row_factory = sqlite3.Row
    try:
        schema = connection.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0]
        videos = connection.execute(
            "SELECT COUNT(*) FROM videos"
        ).fetchone()[0]
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


def validate_entry() -> dict[str, Any]:
    receipt_path = STAGE2_ROOT / "freeze_receipt.private.json"
    if not receipt_path.is_file():
        raise RuntimeError("Stage 2 freeze receipt is missing")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if git("branch", "--show-current") != "codex/v5-d":
        raise RuntimeError("Stage 2 branch identity mismatch")
    if git("rev-parse", "HEAD") != receipt["freeze_commit"]:
        raise RuntimeError("Stage 2 freeze commit mismatch")
    if git("status", "--porcelain"):
        raise RuntimeError("Stage 2 frozen worktree is not clean")
    if corpus_snapshot(STAGE2_ROOT / "isolated/eval.db") != receipt[
        "corpus_snapshot"
    ]:
        raise RuntimeError("Stage 2 corpus/index snapshot drift")
    artifact_manifest = STAGE2_ROOT / "artifact_snapshot.sha256"
    if digest(artifact_manifest.read_bytes()) != receipt[
        "artifact_snapshot_manifest_sha256"
    ]:
        raise RuntimeError("Stage 2 artifact snapshot manifest drift")
    reserve_key = STAGE0_ROOT / "custody/reserve_key.sealed"
    reserve_ciphertext = (
        STAGE0_ROOT / "custody/reserve_manifest.aes256.enc"
    )
    if reserve_key.stat().st_mode & 0o777:
        raise RuntimeError("reserve key is not resealed")
    if digest(reserve_ciphertext.read_bytes()) != receipt[
        "reserve_ciphertext_sha256"
    ]:
        raise RuntimeError("reserve ciphertext drift")
    return receipt


class CapturingBaselineExecutor(ReceiptBoundDeepResearchExecutor):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.last_trace: dict[str, Any] | None = None

    def execute(self, **kwargs: Any):  # type: ignore[no-untyped-def]
        output = super().execute(**kwargs)
        self.last_trace = dict(output.trace)
        return output


def load_phase_cases(
    case_id: str, private_manifest: Path | None
) -> tuple[str, list[dict[str, Any]]]:
    if case_id in SOURCE_CASE_IDS:
        path = STAGE0_ROOT / "custody/discovery_manifest.private.json"
        phase = "source"
    else:
        if private_manifest is None:
            raise RuntimeError("held-out case manifest is custody-only")
        path = private_manifest
        phase = "heldout"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if phase == "source":
        cases = [
            case for case in payload["cases"] if case["case_id"] in SOURCE_CASE_IDS
        ]
    else:
        cases = list(payload["cases"])
        ids = {case["case_id"] for case in cases}
        if len(cases) != 3 or not ids.issubset(set(RESERVE_CASE_IDS)):
            raise RuntimeError(
                "held-out runnable manifest must contain exactly three assigned cases"
            )
    matches = [case for case in cases if case["case_id"] == case_id]
    if len(matches) != 1:
        raise RuntimeError("case identity is absent or ambiguous")
    for case in cases:
        if digest(case["body"]) != case["body_sha256"]:
            raise RuntimeError("case body hash mismatch")
    return phase, cases


def run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--arm", choices=ARMS, required=True)
    parser.add_argument("--outer-attempt", type=int, choices=(1, 2), default=1)
    parser.add_argument("--private-case-manifest", type=Path)
    arguments = parser.parse_args()
    if arguments.case_id not in (*SOURCE_CASE_IDS, *RESERVE_CASE_IDS):
        raise RuntimeError("case is outside the frozen Stage 2 universe")

    receipt = validate_entry()
    phase, phase_cases = load_phase_cases(
        arguments.case_id, arguments.private_case_manifest
    )
    case = next(
        value for value in phase_cases if value["case_id"] == arguments.case_id
    )
    manifest_path = STAGE2_ROOT / "runs/run_manifest.private.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {
            "experiment_id": EXPERIMENT_ID,
            "freeze_commit": receipt["freeze_commit"],
            "freeze_receipt_sha256": digest(
                (STAGE2_ROOT / "freeze_receipt.private.json").read_bytes()
            ),
            "started_at": now(),
            "phase_started_at": {},
            "status": "initialized",
            "credential_access": {
                "status": "not_yet_accessed",
                "value_recorded": False,
            },
            "attempts": [],
        }
    if any(
        attempt["case_id"] == arguments.case_id
        and attempt["arm"] == arguments.arm
        and attempt["outer_attempt"] == arguments.outer_attempt
        for attempt in manifest["attempts"]
    ):
        raise RuntimeError("Stage 2 arm attempt is already recorded")
    if len(manifest["attempts"]) >= 20:
        raise RuntimeError("Stage 2 outer-attempt cap reached")

    if phase not in manifest["phase_started_at"]:
        manifest["phase_started_at"][phase] = now()
    phase_case_ids = tuple(sorted(case["case_id"] for case in phase_cases))
    if phase == "source":
        phase_budget = {
            "max_logical_calls": 104,
            "max_http_attempts": 208,
            "max_input_tokens": 1_060_000,
            "max_output_tokens": 140_000,
            "max_wall_seconds": 5_760,
            "reserve_stop_usd": Decimal("0.16"),
            "absolute_max_cost_usd": Decimal("0.20"),
        }
    else:
        phase_budget = {
            "max_logical_calls": 156,
            "max_http_attempts": 312,
            "max_input_tokens": 1_590_000,
            "max_output_tokens": 210_000,
            "max_wall_seconds": 8_640,
            "reserve_stop_usd": Decimal("0.24"),
            "absolute_max_cost_usd": Decimal("0.30"),
        }
    policy = ProviderRunBudgetPolicy(
        run_id=f"{EXPERIMENT_ID}:{phase}",
        task_ids=task_ids_for_cases(phase_case_ids),
        started_at=manifest["phase_started_at"][phase],
        **phase_budget,
    )
    phase_hashes = manifest.setdefault("phase_budget_policy_hashes", {})
    if phase_hashes.get(phase) not in (None, policy.policy_hash):
        raise RuntimeError("Stage 2 run budget policy drift")
    phase_hashes[phase] = policy.policy_hash
    manifest.setdefault("phase_budget_policies", {})[phase] = policy.manifest()
    write_private(manifest_path, manifest)

    config = load_config(AppPaths.defaults())
    if config.llm_base_url.rstrip("/") != AUTHORIZED_ENDPOINT:
        raise RuntimeError("Provider endpoint mismatch")
    for role in ("query_analysis", "agent_action", "grounded_answer"):
        if config.model_for(role) != AUTHORIZED_MODEL:
            raise RuntimeError(f"Provider model mismatch for {role}")
    app = Application(paths(STAGE2_ROOT / "isolated"))
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
        runner_id="v5-d-stage2-frozen-worker",
    )
    wiring = ReceiptBoundProviderService(
        db=app.db,
        kernel=app.research,
        provider_dispatch_authorized=True,
    )
    for preregistered_case in phase_cases:
        for preregistered_arm in ARMS:
            for preregistered_attempt in (1, 2):
                preregistered_id = task_id(
                    preregistered_case["case_id"],
                    preregistered_arm,
                    preregistered_attempt,
                )
                created = app.research.create_task(
                    command_id=(
                        f"v5d-s2:{EXPERIMENT_ID}:{phase}:"
                        f"{preregistered_case['case_id']}:{preregistered_arm}:"
                        f"A{preregistered_attempt}:create"
                    ),
                    task_id=preregistered_id,
                    objective=preregistered_case["body"],
                    success_constraints=list(
                        preregistered_case["gold_required_aspects"]
                    ),
                    evidence_policy={
                        "authority": "live_current_exact_replay",
                        "product_execution": "receipt_bound_provider",
                        "constraint_profile": "grounded_current_evidence",
                        "experiment_id": EXPERIMENT_ID,
                        "phase": phase,
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
                    _server_constraint_profile=(
                        grounded_current_evidence_profile()
                    ),
                )
                if created["task_id"] != preregistered_id:
                    raise RuntimeError("Stage 2 Task identity mismatch")
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
        executor: Any = ExperimentalReceiptBoundDeepResearchExecutor(
            candidate_path=(
                WORKTREE / "V5_D_CANDIDATE_EVIDENCE_DELTA_FOLLOWUP_V1.json"
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
        "phase": phase,
        "case_id": arguments.case_id,
        "case_body_sha256": case["body_sha256"],
        "arm": arguments.arm,
        "outer_attempt": arguments.outer_attempt,
        "task_id_sha256": digest(identifier),
        "frozen_arm_order": frozen_arm_order(arguments.case_id),
        "started_at": started.isoformat(timespec="microseconds"),
        "status": "running",
    }
    manifest["attempts"].append(record)
    manifest["status"] = "running"
    write_private(manifest_path, manifest)
    attempt_dir = (
        STAGE2_ROOT
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
                f"v5d-s2:{arguments.case_id}:{arguments.arm}:"
                f"A{arguments.outer_attempt}:provider-product-once"
            ),
            max_continuation_cycles=1,
            max_logical_calls=14 if treatment else 12,
            max_http_attempts=28 if treatment else 24,
            max_input_tokens=140_000 if treatment else 125_000,
            max_output_tokens=20_000 if treatment else 15_000,
            max_wall_time_seconds=720,
            case_deadline_at=deadline.isoformat(timespec="microseconds"),
            run_budget=policy,
        )
        result = _settle_running_product_boundary(
            product=product,
            task_id=identifier,
            command_id=(
                f"v5d-s2:{arguments.case_id}:{arguments.arm}:"
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
    manifest.setdefault("phase_budget_snapshots", {})[phase] = jsonable(
        wiring.run_budget_snapshot(policy)
    )
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
                "provider_receipt_count": record.get(
                    "provider_receipt_count", 0
                ),
                "phase_budget_snapshot": manifest["phase_budget_snapshots"][
                    phase
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    run()
