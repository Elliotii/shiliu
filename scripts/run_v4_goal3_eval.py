from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sqlite3
from tempfile import TemporaryDirectory
from typing import Any

from shiliu.app import Application
from shiliu.ask import AskRequest, AskResponse
from shiliu.ask.citations import stable_citation_id
from shiliu.ask.deep.budget import DeepSearchBudget
from shiliu.ask.deep.policy import DEEP_POLICY_VERSION
from shiliu.config import AppPaths, load_config
from shiliu.evidence.authority import bind_live_current_version
from shiliu.evidence.contracts import SourceArtifactReference
from shiliu.evidence.source import load_source_artifact
from shiliu.retrieval.product_search import build_bilibili_jump_url


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPOSITORY_ROOT / "eval" / "v4_goal3_cases.json"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "eval" / "v4_goal3_results.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the bounded six-case V4 Goal 3 real-provider evaluation."
    )
    parser.add_argument(
        "--manifest", type=Path, default=DEFAULT_MANIFEST
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT
    )
    parser.add_argument(
        "--mode", choices=("fast", "deep", "matrix"), default="matrix"
    )
    parser.add_argument(
        "--case", action="append", dest="case_ids",
        help="Run only a named case; may be repeated.",
    )
    parser.add_argument(
        "--no-merge", action="store_true",
        help="Replace rather than merge with existing bounded results.",
    )
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    selected = _selected_runs(
        manifest["cases"], mode=args.mode, case_ids=set(args.case_ids or ())
    )
    if not selected:
        raise SystemExit("No manifest runs matched the requested mode/cases")

    default_paths = AppPaths.defaults()
    if not default_paths.database.is_file() or not default_paths.config.is_file():
        raise SystemExit("Shiliu database or config is unavailable")
    config = load_config(default_paths)
    with TemporaryDirectory(prefix="shiliu-v4-g3-") as temp:
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
        new_results = [
            _run_case(application, case, mode) for case, mode in selected
        ]

    prior: list[dict[str, Any]] = []
    if args.output.is_file() and not args.no_merge:
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        prior = list(existing.get("results", []))
    keys = {
        (str(result.get("case_id")), str(result.get("mode")))
        for result in new_results
    }
    merged = [
        value for value in prior
        if (str(value.get("case_id")), str(value.get("mode"))) not in keys
    ]
    merged.extend(new_results)
    merged.sort(key=lambda value: (str(value["case_id"]), str(value["mode"])))
    payload = {
        "result_version": "v4-goal3-lightweight-eval-v1",
        "manifest_version": manifest["manifest_version"],
        "policy_version": DEEP_POLICY_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "real_provider": True,
        "database_mode": "temporary_snapshot",
        "results": merged,
    }
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0


def _selected_runs(
    cases: list[dict[str, Any]], *, mode: str, case_ids: set[str]
) -> list[tuple[dict[str, Any], str]]:
    selected: list[tuple[dict[str, Any], str]] = []
    for case in cases:
        if case_ids and case["case_id"] not in case_ids:
            continue
        for case_mode in case["modes"]:
            if mode != "matrix" and case_mode != mode:
                continue
            selected.append((case, case_mode))
    return selected


def _run_case(
    application: Application, case: dict[str, Any], mode: str
) -> dict[str, Any]:
    base = {
        "case_id": case["case_id"],
        "category": case["category"],
        "query": case["query"],
        "mode": mode,
        "demo_role": case.get("demo_role"),
        "policy_version": DEEP_POLICY_VERSION if mode == "deep" else None,
        "manual_review": {
            "supportedness": "pending",
            "usefulness": "pending",
            "coverage": "pending",
            "status_honesty": "pending",
            "notes": "",
        },
    }
    try:
        response = application.ask_service.ask(
            AskRequest(query=case["query"], mode=mode)
        )
        trace = application.ask_service.get_trace(response.run_id) or {}
        return {**base, **_bounded_result(application, response, trace)}
    except Exception as exc:
        return {
            **base,
            "runtime_error": f"{type(exc).__name__}: {exc}"[:500],
            "deterministic_checks": {
                "contract_valid": False,
                "budget_respected": False,
            },
        }


def _bounded_result(
    application: Application,
    response: AskResponse,
    trace: dict[str, Any],
) -> dict[str, Any]:
    citation_checks: list[dict[str, Any]] = []
    for citation in response.citations:
        try:
            _validate_citation(application, citation)
            current = True
            error = None
        except Exception as exc:
            current = False
            error = f"{type(exc).__name__}: {exc}"[:300]
        citation_checks.append(
            {
                "citation_id": citation.citation_id,
                "reconstructable": current,
                "error": error,
            }
        )
    budget = DeepSearchBudget()
    summary = response.trace_summary
    finalization = trace.get("finalization")
    finalization = finalization if isinstance(finalization, dict) else trace
    budget_respected = (
        summary.decision_rounds <= budget.max_decision_rounds
        and summary.tool_calls <= budget.max_tool_calls
        and (
            response.mode == "fast"
            or summary.latency_ms <= (budget.total_runtime_seconds * 1000 + 5000)
        )
    )
    return {
        "run_id": response.run_id,
        "status": response.status,
        "termination_reason": response.termination_reason,
        "answer_block_count": len(response.answer_blocks),
        "citation_count": len(response.citations),
        "limitations": list(response.limitations),
        "latency_ms": summary.latency_ms,
        "provider_usage": {
            "query_analysis": trace.get("query_analysis_usage"),
            "agent_action": trace.get("usage"),
            "grounded_answer": finalization.get("answer_usage"),
        },
        "decision_rounds": summary.decision_rounds,
        "tool_calls": summary.tool_calls,
        "repair_used": summary.repair_used,
        "context_truncated": summary.context_truncated,
        "evidence_candidate_dropped_count": (
            summary.evidence_candidate_dropped_count
        ),
        "trace_summary": summary.model_dump(mode="json"),
        "deterministic_checks": _deterministic_checks(
            response,
            citation_checks=citation_checks,
            budget_respected=budget_respected,
        ),
        "review_material": {
            "answer_blocks": [
                {
                    "text": block.text[:800],
                    "citation_ids": list(block.citation_ids),
                }
                for block in response.answer_blocks
            ],
            "citations": [
                {
                    "citation_id": citation.citation_id,
                    "video_title": citation.title,
                    "source_type": citation.source_type,
                    "time_range": [citation.start_time, citation.end_time],
                    "quote_excerpt": citation.quote_text[:500],
                    "jump_url": citation.jump_url,
                }
                for citation in response.citations
            ],
        },
    }


def _deterministic_checks(
    response: AskResponse,
    *,
    citation_checks: list[dict[str, Any]],
    budget_respected: bool,
) -> dict[str, bool]:
    try:
        AskResponse.model_validate(response.model_dump(mode="python"))
        contract_valid = True
    except Exception:
        contract_valid = False

    citation_ids = {value.citation_id for value in response.citations}
    referenced_ids = {
        citation_id
        for block in response.answer_blocks
        for citation_id in block.citation_ids
    }
    blocks_have_citations = all(
        bool(block.citation_ids) for block in response.answer_blocks
    )
    citation_ids_resolve = referenced_ids.issubset(citation_ids)
    reconstructable = (
        len(citation_checks) == len(response.citations)
        and all(
            bool(value.get("reconstructable")) for value in citation_checks
        )
    )
    if response.status == "insufficient":
        answer_shape_valid = (
            not response.answer_blocks and not response.citations
        )
    else:
        answer_shape_valid = bool(response.answer_blocks)
    status_termination_valid = (
        contract_valid
        and response.termination_reason
        == response.trace_summary.termination_reason
        and answer_shape_valid
        and blocks_have_citations
        and citation_ids_resolve
    )
    return {
        "contract_valid": contract_valid,
        "answer_block_citations_present": blocks_have_citations,
        "citation_ids_resolve": citation_ids_resolve,
        "source_identity_current": reconstructable,
        "source_version_current": reconstructable,
        "segments_current": reconstructable,
        "citations_reconstruct_from_current_transcript": reconstructable,
        "stale_not_cited": (
            response.trace_summary.stale_evidence_count == 0
            or reconstructable
        ),
        "status_termination_valid": status_termination_valid,
        "budget_respected": budget_respected,
    }


def _validate_citation(application: Application, citation) -> None:
    video = application.db.get_video(citation.video_id)
    if video is None:
        raise ValueError("citation video is unavailable")
    reference = SourceArtifactReference(
        platform=str(video["platform"]),
        source_id=str(video["source_id"]),
        part=int(video["part"]),
        source_type=str(video.get("subtitle_source") or "unknown"),
        source_language=str(video.get("subtitle_language") or "unknown"),
        artifact_path=str(video.get("raw_subtitle_path") or ""),
    )
    binding = bind_live_current_version(
        reference, db=application.db, video_id=citation.video_id
    )
    if (
        binding.source_artifact_id != citation.source_artifact_id
        or binding.source_version != citation.source_version
    ):
        raise ValueError("citation source identity is stale")
    artifact = load_source_artifact(
        reference, expected_source_version=citation.source_version
    )
    by_id = {value.segment_id: value for value in artifact.segments}
    segments = tuple(by_id[value] for value in citation.segment_ids)
    if any(value.timeline_run_id != citation.timeline_run_id for value in segments):
        raise ValueError("citation crosses transcript timelines")
    expected_id = stable_citation_id(
        source_artifact_id=citation.source_artifact_id,
        source_version=citation.source_version,
        timeline_run_id=citation.timeline_run_id,
        segments=segments,
    )
    quote = "\n".join(
        value.source_text.strip()
        for value in segments
        if value.source_text.strip()
    )
    jump_url = build_bilibili_jump_url(
        str(video.get("video_url") or ""),
        citation.bvid,
        segments[0].start_time,
    )
    if (
        expected_id != citation.citation_id
        or quote != citation.quote_text
        or segments[0].start_time != citation.start_time
        or segments[-1].end_time != citation.end_time
        or jump_url != citation.jump_url
    ):
        raise ValueError("citation projection cannot be reconstructed")


def _snapshot_database(source: Path, target: Path) -> None:
    source_connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    target_connection = sqlite3.connect(target)
    try:
        source_connection.backup(target_connection)
    finally:
        target_connection.close()
        source_connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
