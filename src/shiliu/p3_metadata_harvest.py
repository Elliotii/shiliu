"""Resumable, get_info-only publication-date harvest for a frozen P3 target set."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import random
import sys
import time
from typing import Any, Callable, Iterator

from shiliu.metadata_backfill import validate_candidate

P2_RUN_ID = "pubdate-p2-20260925-small01"
FROZEN_TARGET_SHA256 = "e97b8ee2765c76805ac885c44652349fcc684a8c658ce0dc43a76df3acd649dc"
DEFAULT_CHECKPOINT_REQUESTS = 50
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_MAX_RETRY_AFTER_WAIT = 300.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _append_event(path: Path, event: dict[str, Any]) -> None:
    encoded = (_canonical(event) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, encoded)
        os.fsync(fd)
    finally:
        os.close(fd)
    _fsync_directory(path.parent)


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("harvest_already_running") from exc
        yield
    finally:
        os.close(fd)


def _read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        last_newline = raw.rfind(b"\n")
        # A killed append can leave one partial tail record. Discard only that
        # incomplete record so all previous fsynced events remain recoverable.
        with path.open("r+b") as handle:
            handle.truncate(last_newline + 1 if last_newline >= 0 else 0)
            handle.flush()
            os.fsync(handle.fileno())
        raw = raw[: last_newline + 1] if last_newline >= 0 else b""
    result = []
    for line in raw.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError("harvest_event_log_corrupt") from exc
        if isinstance(value, dict):
            result.append(value)
    return result


def load_target_plan(backup_dir: Path) -> dict[str, Any]:
    """Verify P2 provenance and derive the remaining frozen targets without DB access."""
    root = backup_dir.expanduser().resolve()
    frozen_path = root / "frozen-targets.json"
    candidate_path = root / "p2-candidates.json"
    exception_path = root / "p2-candidate-exceptions.json"
    apply_path = root / "p2-apply-report.json"
    for path in (frozen_path, candidate_path, exception_path, apply_path):
        if not path.is_file():
            raise ValueError("required_p2_evidence_missing")
    frozen_hash = _sha256(frozen_path)
    if frozen_hash != FROZEN_TARGET_SHA256:
        raise ValueError("frozen_target_hash_mismatch")
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    p2_candidates = json.loads(candidate_path.read_text(encoding="utf-8"))
    p2_exceptions = json.loads(exception_path.read_text(encoding="utf-8"))
    apply_report = json.loads(apply_path.read_text(encoding="utf-8"))
    candidate_hash = _sha256(candidate_path)
    apply_counts = apply_report.get("apply", {}).get("counts", {})
    if (
        apply_report.get("run_id") != P2_RUN_ID
        or apply_report.get("apply", {}).get("run_id") != P2_RUN_ID
        or apply_report.get("candidate_sha256") != candidate_hash
        or int(apply_counts.get("applied", -1)) != len(p2_candidates)
    ):
        raise ValueError("p2_success_evidence_mismatch")
    frozen_by_id = {}
    frozen_bvids = set()
    for row in frozen:
        if not isinstance(row, dict):
            raise ValueError("frozen_target_shape_invalid")
        video_id = int(row["video_id"])
        bvid = str(row["bvid"])
        part = int(row["part"])
        if part != 1 or video_id in frozen_by_id or bvid in frozen_bvids:
            raise ValueError("frozen_target_identity_invalid")
        frozen_by_id[video_id] = {"video_id": video_id, "bvid": bvid, "part": part}
        frozen_bvids.add(bvid)
    if len(frozen_by_id) != 2296:
        raise ValueError("frozen_target_count_mismatch")

    p2_candidate_ids = {int(row["video_id"]) for row in p2_candidates}
    applied_ids = {
        int(row["video_id"])
        for row in apply_report.get("video_changes", [])
        if "published_at" in (row.get("changed_columns") or [])
    }
    pending_p2_ids = set()
    for row in p2_exceptions:
        if row.get("error_code") != "upstream_error":
            raise ValueError("unexpected_p2_exception_class")
        pending_p2_ids.add(int(row["video_id"]))
    if (
        len(p2_candidate_ids) != len(p2_candidates)
        or p2_candidate_ids != applied_ids
        or len(applied_ids) != 14
        or len(pending_p2_ids) != 2
        or p2_candidate_ids & pending_p2_ids
        or not (p2_candidate_ids | pending_p2_ids) <= set(frozen_by_id)
    ):
        raise ValueError("p2_target_reconciliation_failed")
    excluded = p2_candidate_ids | pending_p2_ids
    targets = [row for video_id, row in frozen_by_id.items() if video_id not in excluded]
    if len(targets) != 2280:
        raise ValueError("p3_target_count_mismatch")
    return {
        "root": root,
        "targets": targets,
        "frozen_targets_sha256": frozen_hash,
        "p2_candidates_sha256": candidate_hash,
        "p2_apply_report_sha256": _sha256(apply_path),
        "p2_exception_sha256": _sha256(exception_path),
        "p2_run_id": P2_RUN_ID,
        "p2_applied_video_ids": sorted(p2_candidate_ids),
        "p2_pending_retry_video_ids": sorted(pending_p2_ids),
    }


def _events_by_video(events: list[dict[str, Any]]) -> tuple[dict[int, int], dict[int, dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    attempts: dict[int, int] = defaultdict(int)
    latest: dict[int, dict[str, Any]] = {}
    rate_errors: dict[int, list[dict[str, Any]]] = defaultdict(list)
    outstanding: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        video_id = int(event.get("video_id") or 0)
        kind = event.get("type")
        if not video_id:
            continue
        if kind == "attempt_started":
            attempts[video_id] += 1
            outstanding[video_id].append(event)
        elif kind == "attempt_failed":
            if outstanding[video_id]:
                outstanding[video_id].pop(0)
            latest[video_id] = event
            if event.get("classification") == "rate_limit":
                rate_errors[video_id].append(event)
            else:
                rate_errors[video_id] = []
        elif kind in {"target_candidate", "target_exception", "run_stopped"}:
            latest[video_id] = event
            if outstanding[video_id]:
                outstanding[video_id].clear()
            if kind != "run_stopped":
                rate_errors[video_id] = []
    for video_id, starts in outstanding.items():
        if starts and latest.get(video_id, {}).get("type") not in {"target_candidate", "target_exception", "run_stopped"}:
            latest[video_id] = {
                "type": "interrupted_inflight",
                "video_id": video_id,
                "attempts": attempts[video_id],
                "bvid": str(starts[-1].get("bvid") or ""),
            }
    return attempts, latest, rate_errors


def _active_stop(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the newest stop that has not been followed by a retry or resolution."""
    for index in range(len(events) - 1, -1, -1):
        event = events[index]
        if event.get("type") != "run_stopped":
            continue
        video_id = int(event.get("video_id") or 0)
        resumed = any(
            int(later.get("video_id") or 0) == video_id
            and later.get("type") in {"attempt_started", "target_candidate", "target_exception"}
            for later in events[index + 1 :]
        )
        if not resumed:
            return event
    return None


def _last_response_at(events: list[dict[str, Any]]) -> float | None:
    for event in reversed(events):
        kind = event.get("type")
        value = event.get("created_at") if kind in {"attempt_failed", "target_candidate", "target_exception"} else None
        if value is None and kind == "attempt_started":
            value = event.get("started_at")
        if value:
            try:
                return datetime.fromisoformat(str(value)).timestamp()
            except ValueError:
                continue
    return None


def _materialize(events: list[dict[str, Any]], targets: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_video: dict[int, dict[str, Any]] = {}
    for event in events:
        if event.get("type") in {"target_candidate", "target_exception"}:
            by_video[int(event["video_id"])] = event
    order = {int(row["video_id"]): i for i, row in enumerate(targets)}
    terminal = sorted(by_video.values(), key=lambda row: order.get(int(row["video_id"]), 10**9))
    candidates = [row["candidate"] for row in terminal if row.get("type") == "target_candidate"]
    exceptions = [row["exception"] for row in terminal if row.get("type") == "target_exception"]
    return candidates, exceptions


def _error_details(exc: BaseException) -> dict[str, Any]:
    message = str(exc).lower()
    code = str(getattr(exc, "code", type(exc).__name__))
    status = getattr(exc, "http_status", None)
    retry_after = getattr(exc, "retry_after_seconds", None)
    if isinstance(status, bool) or not isinstance(status, int):
        status = None
    if isinstance(retry_after, bool) or not isinstance(retry_after, (int, float)) or not math.isfinite(float(retry_after)):
        retry_after = None
    elif retry_after < 0:
        retry_after = None
    auth = code == "authentication_required" or any(
        token in message for token in ("authentication_required", "credential", "sessdata", "csrf", "-101", "未登录")
    ) or status in {401, 403}
    risk = any(token in message for token in ("验证码", "风控", "captcha", "geetest", "risk control", "operation is too frequent"))
    rate = status in {412, 429} or any(token in message for token in ("-412", "http 412", "status code 412", "status_code 412", "429"))
    unavailable = status in {404, 410} or any(token in message for token in ("-404", "not found", "deleted", "private", "不存在", "已失效"))
    local_failure = code in {"bilibili_cli_missing", "upstream_schema"}
    if auth:
        classification = "authentication_required"
    elif risk:
        classification = "captcha_or_risk_control"
    elif rate:
        classification = "rate_limit"
    elif unavailable:
        classification = "unavailable_or_private"
    elif local_failure:
        classification = "bridge_configuration_or_schema_error"
    elif status is not None and 400 <= status < 500 and status != 408:
        classification = "upstream_http_client_error"
    elif status is not None and status >= 500:
        classification = "upstream_http_server_error"
    elif code in {"upstream_timeout", "upstream_retryable"}:
        classification = "transient_upstream_error"
    elif bool(getattr(exc, "retryable", False)):
        classification = "transient_upstream_error"
    else:
        classification = "upstream_error"
    return {
        "classification": classification,
        "error_code": code,
        "http_status": status,
        "retry_after_seconds": float(retry_after) if retry_after is not None else None,
        "retryable": classification in {"transient_upstream_error", "upstream_http_server_error", "rate_limit"},
        "stop": classification in {
            "authentication_required", "captcha_or_risk_control",
            "bridge_configuration_or_schema_error",
        },
    }


def _candidate_from_response(target: dict[str, Any], data: Any) -> dict[str, Any] | str:
    if not isinstance(data, dict):
        return "response_schema_invalid"
    if data.get("bvid") != target["bvid"]:
        return "identity_mismatch"
    if data.get("source_field") != "info.pubdate":
        return "source_field_mismatch"
    raw = data.get("raw_pubdate")
    published_at = data.get("published_at")
    if published_at is None or isinstance(published_at, bool) or not isinstance(published_at, int) or published_at <= 0:
        return "no_valid_pubdate" if raw is None or published_at is None else "invalid_pubdate_value"
    candidate = {
        "video_id": int(target["video_id"]),
        "bvid": str(target["bvid"]),
        "part": int(target["part"]),
        "platform": "bilibili",
        "source_field": "info.pubdate",
        "raw_pubdate": raw,
        "published_at": published_at,
        "metadata_observed_at": str(data.get("metadata_observed_at") or ""),
        "source": "bilibili.get_info",
    }
    try:
        validate_candidate(candidate)
    except (KeyError, TypeError, ValueError) as exc:
        return f"candidate_validation:{exc}"
    return candidate


def _run_harvest_locked(
    backup_dir: Path,
    fetch_one: Callable[[str], dict[str, Any]],
    *,
    min_interval: float = 2.0,
    max_interval: float = 6.0,
    checkpoint_requests: int = DEFAULT_CHECKPOINT_REQUESTS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    max_retry_after_wait: float = DEFAULT_MAX_RETRY_AFTER_WAIT,
    max_targets: int | None = None,
    resume_stopped: bool = False,
    interval_picker: Callable[[float, float], float] = random.uniform,
    sleep: Callable[[float], None] = time.sleep,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if min_interval < 0 or max_interval < min_interval or checkpoint_requests <= 0 or max_attempts <= 0:
        raise ValueError("harvest_limits_invalid")
    plan = load_target_plan(backup_dir)
    root: Path = plan["root"]
    harvest_dir = root / "p3-harvest"
    harvest_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    segments_dir = harvest_dir / "segments"
    segments_dir.mkdir(mode=0o700, exist_ok=True)
    events_path = harvest_dir / "events.jsonl"
    manifest_path = harvest_dir / "run-manifest.json"
    candidates_path = harvest_dir / "p3-candidates.json"
    exceptions_path = harvest_dir / "p3-exceptions.json"
    events = _read_events(events_path)
    frozen_hash = str(plan["frozen_targets_sha256"])
    existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
    if existing_manifest and existing_manifest.get("frozen_targets_sha256") != frozen_hash:
        raise ValueError("existing_harvest_manifest_mismatch")
    if existing_manifest and existing_manifest.get("p2_apply_report_sha256") != plan["p2_apply_report_sha256"]:
        raise ValueError("existing_p2_apply_evidence_mismatch")
    if existing_manifest and (
        existing_manifest.get("p2_candidate_sha256") != plan["p2_candidates_sha256"]
        or existing_manifest.get("p2_exception_sha256") != plan["p2_exception_sha256"]
        or existing_manifest.get("p3_target_count") != len(plan["targets"])
    ):
        raise ValueError("existing_p2_target_scope_mismatch")
    run_id = str((existing_manifest or {}).get("run_id") or f"pubdate-p3-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{frozen_hash[:8]}")
    if existing_manifest and existing_manifest.get("run_id") != run_id:
        raise ValueError("harvest_run_id_mismatch")
    manifest = existing_manifest or {
        "run_id": run_id,
        "created_at": _utc_now(),
        "state": "running",
        "frozen_target_count": 2296,
        "frozen_targets_sha256": frozen_hash,
        "p2_run_id": plan["p2_run_id"],
        "p2_apply_report_sha256": plan["p2_apply_report_sha256"],
        "p2_candidate_sha256": plan["p2_candidates_sha256"],
        "p2_exception_sha256": plan["p2_exception_sha256"],
        "p2_applied_excluded_count": len(plan["p2_applied_video_ids"]),
        "p2_pending_retry_excluded_count": len(plan["p2_pending_retry_video_ids"]),
        "p2_pending_retry_video_ids": plan["p2_pending_retry_video_ids"],
        "p3_target_count": len(plan["targets"]),
        "get_info_invocations": 0,
        "candidate_count": 0,
        "exception_count": 0,
        "segments_completed": 0,
        "private_content_included": False,
    }
    attempts, latest, rate_errors = _events_by_video(events)
    # A started request with no durable response cannot safely be repeated.
    for target in plan["targets"]:
        vid = int(target["video_id"])
        state = latest.get(vid)
        if state and state.get("type") == "interrupted_inflight":
            event = {
                "type": "target_exception", "video_id": vid, "bvid": target["bvid"],
                "exception": {"video_id": vid, "bvid": target["bvid"], "part": 1,
                              "exception": "interrupted_request_outcome_unknown",
                              "attempts": int(attempts.get(vid, 0))},
                "attempts": int(attempts.get(vid, 0)), "created_at": _utc_now(),
            }
            _append_event(events_path, event)
            events.append(event)
            latest[vid] = event

    candidates, exceptions = _materialize(events, plan["targets"])
    _atomic_json(candidates_path, candidates)
    _atomic_json(exceptions_path, exceptions)

    stopped = _active_stop(events)
    if stopped and (not resume_stopped or stopped.get("reason") == "persistent_rate_limit"):
        manifest.update({"state": "stopped", "stop_reason": stopped.get("reason"), "updated_at": _utc_now()})
        _atomic_json(manifest_path, manifest)
        return _summary(manifest, plan, latest, candidates, exceptions, stopped.get("reason"))
    if stopped and resume_stopped:
        resume_after = stopped.get("not_before_utc")
        if resume_after:
            due = datetime.fromisoformat(str(resume_after))
            delay = (due - datetime.now(timezone.utc)).total_seconds()
            if delay > 0:
                manifest.update({"state": "stopped", "stop_reason": "retry_after_not_elapsed", "retry_after_not_before_utc": resume_after, "updated_at": _utc_now()})
                _atomic_json(manifest_path, manifest)
                return _summary(manifest, plan, latest, candidates, exceptions, "retry_after_not_elapsed")

    segment_files = sorted(segments_dir.glob("segment-*.json"))
    segment_number = len(segment_files) + 1
    checkpoint_indices = [i for i, event in enumerate(events) if event.get("type") == "checkpoint"]
    checkpoint_index = checkpoint_indices[-1] if checkpoint_indices else -1
    segment_events: list[dict[str, Any]] = list(events[checkpoint_index + 1 :])
    calls_since_checkpoint = sum(1 for event in segment_events if event.get("type") == "attempt_started")
    segment_started = str(events[checkpoint_index].get("created_at") or _utc_now()) if checkpoint_indices else _utc_now()
    previous_call_at = _last_response_at(events)
    newly_resolved = 0
    stop_reason: str | None = None
    last_completed: dict[str, Any] | None = None
    for target in plan["targets"]:
        if latest.get(int(target["video_id"]), {}).get("type") in {"target_candidate", "target_exception"}:
            last_completed = target

    def checkpoint(state: str, *, force: bool = False, reason: str | None = None) -> None:
        nonlocal segment_number, segment_started, segment_events, calls_since_checkpoint
        current_candidates, current_exceptions = _materialize(events, plan["targets"])
        _atomic_json(candidates_path, current_candidates)
        _atomic_json(exceptions_path, current_exceptions)
        if force or calls_since_checkpoint >= checkpoint_requests or state in {"stopped", "complete", "interrupted", "partial"}:
            segment_path = segments_dir / f"segment-{segment_number:04d}.json"
            segment_request_count = sum(1 for event in segment_events if event.get("type") == "attempt_started")
            classifications = Counter(
                str(event.get("classification"))
                for event in segment_events if event.get("type") == "attempt_failed"
            )
            segment = {
                "run_id": run_id, "segment": segment_number,
                "started_at": segment_started, "completed_at": _utc_now(),
                "frozen_targets_sha256": frozen_hash,
                "get_info_invocations": segment_request_count,
                "attempt_failures_by_classification": dict(classifications),
                "new_candidates": sum(1 for event in segment_events if event.get("type") == "target_candidate"),
                "new_exceptions": sum(1 for event in segment_events if event.get("type") == "target_exception"),
                "stop_reason": reason,
                "candidate_sha256": _sha256(candidates_path),
                "exception_sha256": _sha256(exceptions_path),
                "event_log_sha256": _sha256(events_path) if events_path.exists() else hashlib.sha256(b"").hexdigest(),
                "checkpoint_video_id": (last_completed or {}).get("video_id"),
                "checkpoint_bvid": (last_completed or {}).get("bvid"),
            }
            _atomic_json(segment_path, segment)
            checkpoint_event = {
                "type": "checkpoint", "segment": segment_number,
                "created_at": _utc_now(),
                "get_info_invocations": sum(1 for event in events if event.get("type") == "attempt_started"),
                "candidate_sha256": segment["candidate_sha256"],
                "exception_sha256": segment["exception_sha256"],
            }
            _append_event(events_path, checkpoint_event)
            events.append(checkpoint_event)
            segment_number += 1
            segment_started = _utc_now()
            segment_events = []
            calls_since_checkpoint = 0
        current_attempts, current_latest, _ = _events_by_video(events)
        terminal_success = sum(1 for event in current_latest.values() if event.get("type") == "target_candidate")
        terminal_exceptions = sum(1 for event in current_latest.values() if event.get("type") == "target_exception")
        terminal = terminal_success + terminal_exceptions
        remaining = len(plan["targets"]) - terminal
        manifest.update({
            "state": state, "updated_at": _utc_now(),
            "get_info_invocations": sum(1 for event in events if event.get("type") == "attempt_started"),
            "candidate_count": len(current_candidates), "exception_count": len(current_exceptions),
            "targets_terminal": terminal, "targets_remaining": remaining,
            "segments_completed": segment_number - 1,
            "last_completed_video_id": (last_completed or {}).get("video_id"),
            "last_completed_bvid": (last_completed or {}).get("bvid"),
            "last_checkpoint_at": _utc_now(),
            "candidate_sha256": _sha256(candidates_path),
            "exception_sha256": _sha256(exceptions_path),
            "stop_reason": reason,
            "p2_pending_retry_status": "excluded_from_p3_first_pass",
        })
        if previous_call_at is not None:
            manifest["last_get_info_response_at"] = datetime.fromtimestamp(previous_call_at, timezone.utc).isoformat(timespec="seconds")
        _atomic_json(manifest_path, manifest)
        if progress:
            progress({"state": state, "get_info_invocations": manifest["get_info_invocations"],
                      "candidates": len(current_candidates), "exceptions": len(current_exceptions),
                      "remaining": remaining, "stop_reason": reason})

    # Recover a complete checkpoint if the prior process stopped after fsyncing
    # events but before replacing the materialized files and manifest.
    checkpoint("running", force=calls_since_checkpoint > 0 or (bool(events) and not existing_manifest))

    try:
        for target in plan["targets"]:
            video_id = int(target["video_id"])
            current_state = latest.get(video_id)
            if current_state and current_state.get("type") in {"target_candidate", "target_exception"}:
                continue
            if max_targets is not None and newly_resolved >= max_targets:
                break
            previous_errors = [event for event in events if int(event.get("video_id") or 0) == video_id and event.get("type") == "attempt_failed"]
            if previous_errors and previous_errors[-1].get("classification") in {"rate_limit", "authentication_required", "captcha_or_risk_control"} and not resume_stopped:
                stop_reason = "prior_stop_requires_explicit_resume"
                checkpoint("stopped", force=True, reason=stop_reason)
                return _summary(manifest, plan, latest, candidates, exceptions, stop_reason)
            rate_streak = len(rate_errors.get(video_id, []))
            if rate_streak >= 2:
                stop_reason = "persistent_rate_limit"
                checkpoint("stopped", force=True, reason=stop_reason)
                return _summary(manifest, plan, latest, candidates, exceptions, stop_reason)
            next_retry_after: float | None = None
            last_attempt_count = int(attempts.get(video_id, 0))
            resolved_this_target = False
            for attempt in range(last_attempt_count + 1, max_attempts + 1):
                if previous_call_at is not None:
                    base_delay = float(interval_picker(min_interval, max_interval))
                    elapsed = time.time() - previous_call_at
                    delay = max(0.0, base_delay - elapsed, next_retry_after or 0.0)
                    if delay > 0:
                        sleep(delay)
                started_at = _utc_now()
                start_event = {"type": "attempt_started", "video_id": video_id, "bvid": target["bvid"], "attempt": attempt, "started_at": started_at}
                _append_event(events_path, start_event)
                events.append(start_event); segment_events.append(start_event)
                attempts[video_id] = attempt
                calls_since_checkpoint += 1
                try:
                    data = fetch_one(str(target["bvid"]))
                except Exception as exc:
                    details = _error_details(exc)
                    failure = {"type": "attempt_failed", "video_id": video_id, "bvid": target["bvid"],
                               "attempt": attempt, "created_at": _utc_now(), **details}
                    _append_event(events_path, failure); events.append(failure); segment_events.append(failure)
                    previous_call_at = datetime.fromisoformat(failure["created_at"]).timestamp()
                    latest[video_id] = failure
                    if details["classification"] == "rate_limit":
                        rate_streak += 1; rate_errors[video_id].append(failure)
                    else:
                        rate_streak = 0; rate_errors[video_id] = []
                    if details["stop"]:
                        stop_reason = details["classification"]
                        stop_event = {"type": "run_stopped", "video_id": video_id, "bvid": target["bvid"],
                                      "attempt": attempt, "created_at": _utc_now(), "reason": stop_reason,
                                      "error_code": details["error_code"]}
                        _append_event(events_path, stop_event); events.append(stop_event); segment_events.append(stop_event)
                        latest[video_id] = stop_event
                        checkpoint("stopped", force=True, reason=stop_reason)
                        return _summary(manifest, plan, latest, candidates, exceptions, stop_reason)
                    if details["classification"] == "rate_limit":
                        retry_after = details["retry_after_seconds"]
                        if retry_after is None or retry_after <= 0 or rate_streak >= 2 or attempt >= max_attempts:
                            stop_reason = "persistent_rate_limit" if rate_streak >= 2 else "rate_limit_without_safe_retry"
                            stop_event = {"type": "run_stopped", "video_id": video_id, "bvid": target["bvid"],
                                          "attempt": attempt, "created_at": _utc_now(), "reason": stop_reason,
                                          "error_code": details["error_code"], "retry_after_seconds": retry_after}
                            if retry_after and retry_after > 0:
                                stop_event["not_before_utc"] = (datetime.now(timezone.utc) + timedelta(seconds=retry_after)).isoformat(timespec="seconds")
                            _append_event(events_path, stop_event); events.append(stop_event); segment_events.append(stop_event)
                            latest[video_id] = stop_event
                            checkpoint("stopped", force=True, reason=stop_reason)
                            return _summary(manifest, plan, latest, candidates, exceptions, stop_reason)
                        if retry_after > max_retry_after_wait:
                            stop_reason = "retry_after_deferred"
                            stop_event = {"type": "run_stopped", "video_id": video_id, "bvid": target["bvid"],
                                          "attempt": attempt, "created_at": _utc_now(), "reason": stop_reason,
                                          "error_code": details["error_code"], "retry_after_seconds": retry_after,
                                          "not_before_utc": (datetime.now(timezone.utc) + timedelta(seconds=retry_after)).isoformat(timespec="seconds")}
                            _append_event(events_path, stop_event); events.append(stop_event); segment_events.append(stop_event)
                            latest[video_id] = stop_event
                            checkpoint("stopped", force=True, reason=stop_reason)
                            return _summary(manifest, plan, latest, candidates, exceptions, stop_reason)
                        next_retry_after = float(retry_after)
                        if calls_since_checkpoint >= checkpoint_requests:
                            checkpoint("running", force=True)
                        continue
                    if details["classification"] in {"unavailable_or_private", "upstream_http_client_error"}:
                        exception = {"video_id": video_id, "bvid": target["bvid"], "part": 1,
                                     "exception": details["classification"], "attempts": attempt,
                                     "error_code": details["error_code"], "http_status": details["http_status"]}
                        event = {"type": "target_exception", "video_id": video_id, "bvid": target["bvid"],
                                 "exception": exception, "attempts": attempt, "created_at": _utc_now()}
                        _append_event(events_path, event); events.append(event); segment_events.append(event)
                        latest[video_id] = event; newly_resolved += 1; last_completed = target; resolved_this_target = True
                        break
                    if not details["retryable"] or attempt >= max_attempts:
                        exception = {"video_id": video_id, "bvid": target["bvid"], "part": 1,
                                     "exception": "transient_exhausted" if details["retryable"] else details["classification"],
                                     "attempts": attempt, "error_code": details["error_code"],
                                     "http_status": details["http_status"]}
                        event = {"type": "target_exception", "video_id": video_id, "bvid": target["bvid"],
                                 "exception": exception, "attempts": attempt, "created_at": _utc_now()}
                        _append_event(events_path, event); events.append(event); segment_events.append(event)
                        latest[video_id] = event; newly_resolved += 1; last_completed = target; resolved_this_target = True
                        break
                    retry_after = details["retry_after_seconds"]
                    if retry_after is not None and retry_after > max_retry_after_wait:
                        stop_reason = "retry_after_deferred"
                        stop_event = {"type": "run_stopped", "video_id": video_id, "bvid": target["bvid"],
                                      "attempt": attempt, "created_at": _utc_now(), "reason": stop_reason,
                                      "error_code": details["error_code"], "retry_after_seconds": retry_after,
                                      "not_before_utc": (datetime.now(timezone.utc) + timedelta(seconds=retry_after)).isoformat(timespec="seconds")}
                        _append_event(events_path, stop_event); events.append(stop_event); segment_events.append(stop_event)
                        latest[video_id] = stop_event
                        checkpoint("stopped", force=True, reason=stop_reason)
                        return _summary(manifest, plan, latest, candidates, exceptions, stop_reason)
                    next_retry_after = float(retry_after) if retry_after is not None else min(6.0, float(2 ** attempt))
                    if calls_since_checkpoint >= checkpoint_requests:
                        checkpoint("running", force=True)
                    continue
                outcome = _candidate_from_response(target, data)
                if isinstance(outcome, str):
                    if outcome in {"identity_mismatch", "source_field_mismatch", "response_schema_invalid"}:
                        stop_reason = outcome
                        stop_event = {"type": "run_stopped", "video_id": video_id, "bvid": target["bvid"],
                                      "attempt": attempt, "created_at": _utc_now(), "reason": stop_reason}
                        _append_event(events_path, stop_event); events.append(stop_event); segment_events.append(stop_event)
                        latest[video_id] = stop_event
                        checkpoint("stopped", force=True, reason=stop_reason)
                        return _summary(manifest, plan, latest, candidates, exceptions, stop_reason)
                    exception = {"video_id": video_id, "bvid": target["bvid"], "part": 1,
                                 "exception": outcome, "attempts": attempt,
                                 "raw_pubdate": data.get("raw_pubdate") if data.get("raw_pubdate") is None or isinstance(data.get("raw_pubdate"), (int, float, str, bool)) else {"type": type(data.get("raw_pubdate")).__name__}}
                    event = {"type": "target_exception", "video_id": video_id, "bvid": target["bvid"],
                             "exception": exception, "attempts": attempt, "created_at": _utc_now()}
                    _append_event(events_path, event); events.append(event); segment_events.append(event)
                    latest[video_id] = event; newly_resolved += 1; last_completed = target; resolved_this_target = True
                else:
                    event = {"type": "target_candidate", "video_id": video_id, "bvid": target["bvid"],
                             "candidate": outcome, "attempts": attempt, "created_at": _utc_now()}
                    _append_event(events_path, event); events.append(event); segment_events.append(event)
                    latest[video_id] = event; newly_resolved += 1; last_completed = target; resolved_this_target = True
                previous_call_at = datetime.fromisoformat(event["created_at"]).timestamp()
                latest[video_id] = event
                if calls_since_checkpoint >= checkpoint_requests:
                    checkpoint("running", force=True)
                break
            if not resolved_this_target and latest.get(video_id, {}).get("type") not in {"run_stopped", "target_candidate", "target_exception"}:
                exception = {"video_id": video_id, "bvid": target["bvid"], "part": 1,
                             "exception": "transient_exhausted", "attempts": int(attempts.get(video_id, 0)),
                             "error_code": "attempt_limit"}
                event = {"type": "target_exception", "video_id": video_id, "bvid": target["bvid"],
                         "exception": exception, "attempts": exception["attempts"], "created_at": _utc_now()}
                _append_event(events_path, event); events.append(event); segment_events.append(event)
                latest[video_id] = event; newly_resolved += 1; last_completed = target
            if latest.get(video_id, {}).get("type") == "run_stopped":
                stop_reason = str(latest[video_id].get("reason") or "stopped")
                checkpoint("stopped", force=True, reason=stop_reason)
                return _summary(manifest, plan, latest, candidates, exceptions, stop_reason)
            if calls_since_checkpoint >= checkpoint_requests:
                checkpoint("running", force=True)
    except KeyboardInterrupt:
        checkpoint("interrupted", force=True, reason="interrupted_by_operator")
        return _summary(manifest, plan, latest, *_materialize(events, plan["targets"]), "interrupted_by_operator")

    candidates, exceptions = _materialize(events, plan["targets"])
    attempts, latest, _ = _events_by_video(events)
    remaining = len(plan["targets"]) - sum(1 for e in latest.values() if e.get("type") in {"target_candidate", "target_exception"})
    state = "complete" if remaining == 0 else "partial"
    checkpoint(state, force=True)
    return _summary(manifest, plan, latest, candidates, exceptions, None)


def run_harvest(
    backup_dir: Path,
    fetch_one: Callable[[str], dict[str, Any]],
    **options: Any,
) -> dict[str, Any]:
    """Serialize one harvest process per backup directory and resume its ledger."""
    root = Path(backup_dir).expanduser().resolve()
    harvest_dir = root / "p3-harvest"
    with _exclusive_lock(harvest_dir / ".lock"):
        return _run_harvest_locked(root, fetch_one, **options)


def _summary(manifest: dict[str, Any], plan: dict[str, Any], latest: dict[int, dict[str, Any]],
             candidates: list[dict[str, Any]], exceptions: list[dict[str, Any]], stop_reason: str | None) -> dict[str, Any]:
    terminal = sum(1 for event in latest.values() if event.get("type") in {"target_candidate", "target_exception"})
    return {
        "run_id": manifest.get("run_id"), "state": manifest.get("state"),
        "frozen_targets_sha256": plan["frozen_targets_sha256"],
        "target_count": len(plan["targets"]), "targets_terminal": terminal,
        "targets_remaining": len(plan["targets"]) - terminal,
        "get_info_invocations": manifest.get("get_info_invocations", 0),
        "candidate_count": len(candidates), "exception_count": len(exceptions),
        "candidate_sha256": manifest.get("candidate_sha256"),
        "exception_sha256": manifest.get("exception_sha256"),
        "stop_reason": stop_reason,
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--checkpoint-requests", type=int, default=DEFAULT_CHECKPOINT_REQUESTS)
    parser.add_argument("--min-interval", type=float, default=2.0)
    parser.add_argument("--max-interval", type=float, default=6.0)
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument("--max-retry-after-wait", type=float, default=DEFAULT_MAX_RETRY_AFTER_WAIT)
    parser.add_argument("--max-targets", type=int)
    parser.add_argument("--resume-stopped", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        from shiliu.bilibili import BilibiliAdapter
        from shiliu.config import load_config

        config = load_config()
        adapter = BilibiliAdapter(Path(config.bili_cli_root), timeout_seconds=45)
        result = run_harvest(
            args.backup_dir,
            adapter.fetch_video_pubdate,
            min_interval=args.min_interval,
            max_interval=args.max_interval,
            checkpoint_requests=args.checkpoint_requests,
            max_attempts=args.max_attempts,
            max_retry_after_wait=args.max_retry_after_wait,
            max_targets=args.max_targets,
            resume_stopped=args.resume_stopped,
            progress=lambda item: print(_canonical(item), flush=True),
        )
        print(_canonical(result), flush=True)
        return 0 if result["state"] in {"complete", "partial", "stopped", "interrupted"} else 1
    except Exception as exc:
        # Only the exception class and controlled message cross the CLI boundary.
        print(_canonical({"error": type(exc).__name__, "message": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
