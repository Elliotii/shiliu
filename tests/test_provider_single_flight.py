from __future__ import annotations

import fcntl
import json
import multiprocessing
import os
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import BaseModel

from shiliu.domain import PipelineError
from shiliu.db import Database, utc_now
from shiliu.llm import CompletionResponse
from shiliu.taxonomy.model_calls import AuditedJsonCaller
from shiliu.taxonomy.provider_single_flight import (
    ImmutableResponseLedger,
    ProviderAttemptScope,
    ProviderLeaseConfig,
    ProviderSingleFlight,
)
from shiliu.taxonomy.run_repository import TaxonomyRunRepository


class TinyOutput(BaseModel):
    value: str


def _increment(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.seek(0)
        value = int(handle.read().strip() or "0") + 1
        handle.seek(0)
        handle.truncate()
        handle.write(str(value))
        handle.flush()
        os.fsync(handle.fileno())
        return value


class FileBlockingProvider:
    model = "fake"
    thinking_enabled = False
    reasoning_effort = None

    def __init__(
        self,
        *,
        counter: Path,
        started: Path | None = None,
        release: Path | None = None,
        content: str = '{"value":"ok"}',
        response_id: str = "fake-response",
    ) -> None:
        self.counter = counter
        self.started = started
        self.release = release
        self.content = content
        self.response_id = response_id

    def complete_raw(self, prompt: str, *, max_tokens: int | None = None):
        _increment(self.counter)
        if self.started:
            self.started.write_text("started", encoding="utf-8")
        if self.release:
            deadline = time.monotonic() + 5
            while not self.release.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
        return CompletionResponse(
            self.content,
            "stop",
            {"prompt_tokens": 1, "completion_tokens": 1},
            self.response_id,
        )


def _caller_worker(
    call_dir: str,
    counter: str,
    started: str | None,
    release: str | None,
    queue,
) -> None:
    provider = FileBlockingProvider(
        counter=Path(counter),
        started=Path(started) if started else None,
        release=Path(release) if release else None,
    )
    caller = AuditedJsonCaller(
        provider=provider,  # type: ignore[arg-type]
        repair_provider=provider,  # type: ignore[arg-type]
        lease_config=ProviderLeaseConfig(lease_seconds=2, heartbeat_interval_seconds=0.05),
    )
    path = Path(call_dir)
    try:
        result, _ = caller.call(
            call_dir=path,
            prompt="PROMPT",
            prompt_version="v1",
            schema=TinyOutput,
            schema_hint='{"value":"string"}',
            max_tokens=20,
            input_ids=["C001"],
            resume=path.exists(),
            lease_scope=ProviderAttemptScope(1, "stage", "main", "attempt-01"),
        )
    except PipelineError as exc:
        queue.put(("error", exc.code))
    else:
        queue.put(("ok", result.value))


def _repair_worker(
    call_dir: str,
    primary_counter: str,
    repair_counter: str,
    repair_started: str,
    repair_release: str,
    queue,
) -> None:
    primary = FileBlockingProvider(
        counter=Path(primary_counter),
        content='{"wrong":1}',
        response_id="primary-invalid",
    )
    repair = FileBlockingProvider(
        counter=Path(repair_counter),
        started=Path(repair_started),
        release=Path(repair_release),
        content='{"value":"fixed"}',
        response_id="repair-valid",
    )
    caller = AuditedJsonCaller(
        provider=primary,  # type: ignore[arg-type]
        repair_provider=repair,  # type: ignore[arg-type]
        lease_config=ProviderLeaseConfig(lease_seconds=2, heartbeat_interval_seconds=0.05),
    )
    path = Path(call_dir)
    try:
        result, _ = caller.call(
            call_dir=path,
            prompt="PROMPT",
            prompt_version="v1",
            schema=TinyOutput,
            schema_hint='{"value":"string"}',
            max_tokens=20,
            input_ids=["C001"],
            resume=path.exists(),
            lease_scope=ProviderAttemptScope(1, "stage", "main", "attempt-01"),
        )
    except PipelineError as exc:
        queue.put(("error", exc.code))
    else:
        queue.put(("ok", result.value))


def _wait_for(path: Path) -> None:
    deadline = time.monotonic() + 5
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert path.exists()


def _count(path: Path) -> int:
    return int(path.read_text() or "0") if path.exists() else 0


def test_same_attempt_two_processes_call_provider_once(tmp_path):
    context = multiprocessing.get_context("fork")
    queue = context.Queue()
    call_dir = tmp_path / "run-000001" / "stage" / "main" / "attempt-01"
    counter = tmp_path / "count"
    started = tmp_path / "started"
    release = tmp_path / "release"
    args = tuple(map(str, (call_dir, counter, started, release))) + (queue,)
    first = context.Process(target=_caller_worker, args=args)
    first.start()
    _wait_for(started)
    second = context.Process(target=_caller_worker, args=args)
    second.start()
    second.join(5)
    release.write_text("release", encoding="utf-8")
    first.join(5)

    results = {queue.get(timeout=2), queue.get(timeout=2)}
    assert _count(counter) == 1
    assert ("ok", "ok") in results
    assert ("error", "provider_already_in_progress") in results
    assert not (call_dir.parent / "attempt-02").exists()
    assert json.loads((call_dir / "audit.json").read_text())["status"] == "completed"


def test_different_units_can_call_in_parallel(tmp_path):
    barrier = threading.Barrier(2)
    active = 0
    maximum = 0
    lock = threading.Lock()

    def invoke(unit: str) -> None:
        nonlocal active, maximum
        call_dir = tmp_path / "run-000001" / "stage" / unit / "attempt-01"
        flight = ProviderSingleFlight(
            call_dir=call_dir,
            scope=ProviderAttemptScope(1, "stage", unit, "attempt-01"),
            config=ProviderLeaseConfig(2, 0.05),
        )

        def provider_call():
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
            barrier.wait(timeout=2)
            with lock:
                active -= 1
            return CompletionResponse('{"value":"ok"}', "stop", None, unit)

        flight.invoke(
            provider_call=provider_call,
            request_kind="primary",
            prompt_hash="prompt",
            schema_hash="schema",
        )

    threads = [threading.Thread(target=invoke, args=(f"batch-{i}",)) for i in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(3)
    assert maximum == 2


def test_second_runner_reuses_processing_attempt_number(tmp_path):
    db = Database(tmp_path / "state.db")
    db.initialize()
    now = utc_now()
    with db.connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO taxonomy_runs(
                run_kind, status, current_stage, corpus_snapshot_id,
                engine, engine_version, parameters_json, search_enabled,
                created_at, updated_at
            ) VALUES('test', 'pending', NULL, NULL, 'test', 'v1', '{}', 0, ?, ?)
            """,
            (now, now),
        )
        run_id = int(cursor.lastrowid)
    repository = TaxonomyRunRepository(db)
    kwargs = {
        "input_hash": "input",
        "model": "fake",
        "prompt_version": "v1",
        "thinking_enabled": False,
        "reasoning_effort": None,
    }

    first = repository.start_stage(run_id, "stage", "main", **kwargs)
    second = repository.start_stage(run_id, "stage", "main", **kwargs)

    assert first["attempt_count"] == second["attempt_count"] == 1

    recovered = repository.start_stage(
        run_id,
        "stage",
        "main",
        **kwargs,
        force_new_attempt=True,
        expected_attempt_count=1,
    )
    competing_recovery = repository.start_stage(
        run_id,
        "stage",
        "main",
        **kwargs,
        force_new_attempt=True,
        expected_attempt_count=1,
    )
    assert recovered["attempt_count"] == competing_recovery["attempt_count"] == 2


def test_resume_uses_persisted_ledger_raw_without_provider(tmp_path):
    call_dir = tmp_path / "call"
    scope = ProviderAttemptScope(1, "stage", "main", "attempt-01")
    flight = ProviderSingleFlight(
        call_dir=call_dir, scope=scope, config=ProviderLeaseConfig(2, 0.05)
    )
    calls = 0

    def first_call():
        nonlocal calls
        calls += 1
        return CompletionResponse('{"value":"persisted"}', "stop", None, "raw-1")

    flight.invoke(
        provider_call=first_call,
        request_kind="primary",
        prompt_hash="prompt",
        schema_hash="schema",
    )
    (call_dir / "prompt.txt").write_text("PROMPT", encoding="utf-8")
    (call_dir / "audit.json").write_text(json.dumps({
        "status": "prepared",
        "prompt_version": "v1",
        "prompt_path": "prompt.txt",
        "input_ids": ["C001"],
        "request_attempt_count": 1,
    }), encoding="utf-8")

    class MustNotCall(FileBlockingProvider):
        def complete_raw(self, prompt: str, *, max_tokens: int | None = None):
            raise AssertionError("ledger raw exists")

    provider = MustNotCall(counter=tmp_path / "never")
    result, _ = AuditedJsonCaller(
        provider=provider,  # type: ignore[arg-type]
        repair_provider=provider,  # type: ignore[arg-type]
        lease_config=ProviderLeaseConfig(2, 0.05),
    ).call(
        call_dir=call_dir,
        prompt="PROMPT",
        prompt_version="v1",
        schema=TinyOutput,
        schema_hint='{"value":"string"}',
        max_tokens=20,
        input_ids=["C001"],
        resume=True,
        lease_scope=scope,
    )
    assert result.value == "persisted"
    assert calls == 1


def test_repair_is_single_flight(tmp_path):
    context = multiprocessing.get_context("fork")
    queue = context.Queue()
    call_dir = tmp_path / "run-000001" / "stage" / "main" / "attempt-01"
    primary_counter = tmp_path / "primary-count"
    repair_counter = tmp_path / "repair-count"
    repair_started = tmp_path / "repair-started"
    repair_release = tmp_path / "repair-release"
    args = tuple(map(str, (
        call_dir, primary_counter, repair_counter, repair_started, repair_release,
    ))) + (queue,)
    first = context.Process(target=_repair_worker, args=args)
    first.start()
    _wait_for(repair_started)
    second = context.Process(target=_repair_worker, args=args)
    second.start()
    second.join(5)
    repair_release.write_text("release", encoding="utf-8")
    first.join(5)
    results = {queue.get(timeout=2), queue.get(timeout=2)}
    assert _count(primary_counter) == 1
    assert _count(repair_counter) == 1
    assert ("ok", "fixed") in results
    assert ("error", "provider_already_in_progress") in results
    repair_audit = json.loads((call_dir / "repair-audit.json").read_text())
    assert repair_audit["status"] == "completed"
    assert repair_audit["raw_response_path"].startswith(
        "responses/json_repair/response-"
    )


def _write_expired_lease(
    call_dir: Path, *, pid: int | None, hostname: str | None,
) -> None:
    lease_dir = call_dir / "leases"
    lease_dir.mkdir(parents=True)
    expired = (
        datetime.now(timezone.utc) - timedelta(seconds=10)
    ).isoformat(timespec="milliseconds")
    (lease_dir / "primary.json").write_text(json.dumps({
        "version": "provider-attempt-lease-v1",
        "run_id": 1,
        "stage_name": "stage",
        "unit_key": "main",
        "attempt_id": "attempt-01",
        "request_kind": "primary",
        "state": "requesting",
        "owner_id": "dead-owner",
        "pid": pid,
        "hostname": hostname,
        "lease_expires_at": expired,
        "raw_response_path": None,
        "provider_response_received_at": None,
    }), encoding="utf-8")


def test_expired_dead_owner_abandons_old_attempt_and_new_attempt_can_call(tmp_path):
    old = tmp_path / "run-000001" / "stage" / "main" / "attempt-01"
    _write_expired_lease(old, pid=99999999, hostname=socket.gethostname())
    flight = ProviderSingleFlight(
        call_dir=old,
        scope=ProviderAttemptScope(1, "stage", "main", "attempt-01"),
        config=ProviderLeaseConfig(1, 0.05),
    )
    with pytest.raises(PipelineError) as error:
        flight.invoke(
            provider_call=lambda: CompletionResponse("{}", "stop", None, "bad"),
            request_kind="primary",
            prompt_hash="prompt",
            schema_hash="schema",
        )
    assert error.value.code == "provider_attempt_abandoned_new_attempt_required"
    assert (old / "attempt-abandoned.json").is_file()
    assert json.loads((old / "leases" / "primary.json").read_text())["state"] == (
        "abandoned"
    )

    new = old.parent / "attempt-02"
    invocation = ProviderSingleFlight(
        call_dir=new,
        scope=ProviderAttemptScope(1, "stage", "main", "attempt-02"),
        config=ProviderLeaseConfig(1, 0.05),
    ).invoke(
        provider_call=lambda: CompletionResponse("{}", "stop", None, "new"),
        request_kind="primary",
        prompt_hash="prompt",
        schema_hash="schema",
    )
    assert invocation.response.response_id == "new"
    assert old.is_dir() and new.is_dir()


def test_expired_lease_with_missing_owner_is_conservative(tmp_path):
    call_dir = tmp_path / "run-000001" / "stage" / "main" / "attempt-01"
    _write_expired_lease(call_dir, pid=None, hostname=None)
    calls = 0

    def provider_call():
        nonlocal calls
        calls += 1
        return CompletionResponse("{}", "stop", None, "never")

    with pytest.raises(PipelineError) as error:
        ProviderSingleFlight(
            call_dir=call_dir,
            scope=ProviderAttemptScope(1, "stage", "main", "attempt-01"),
            config=ProviderLeaseConfig(1, 0.05),
        ).invoke(
            provider_call=provider_call,
            request_kind="primary",
            prompt_hash="prompt",
            schema_hash="schema",
        )
    assert error.value.code == "provider_lease_owner_unconfirmed"
    assert calls == 0


def test_response_ledger_prevents_resend_when_audit_not_updated(tmp_path):
    call_dir = tmp_path / "run-000001" / "stage" / "main" / "attempt-01"
    flight = ProviderSingleFlight(
        call_dir=call_dir,
        scope=ProviderAttemptScope(1, "stage", "main", "attempt-01"),
        config=ProviderLeaseConfig(2, 0.05),
    )
    first = flight.invoke(
        provider_call=lambda: CompletionResponse("raw", "stop", None, "response"),
        request_kind="primary",
        prompt_hash="prompt",
        schema_hash="schema",
    )
    calls = 0

    def must_not_call():
        nonlocal calls
        calls += 1
        return CompletionResponse("other", "stop", None, "other")

    resumed = flight.invoke(
        provider_call=must_not_call,
        request_kind="primary",
        prompt_hash="prompt",
        schema_hash="schema",
    )
    assert resumed.resumed_from_ledger is True
    assert resumed.raw_sha256 == first.raw_sha256
    assert calls == 0


def test_two_recovery_runners_call_each_request_kind_once(tmp_path):
    # This reproduces the foreground + launchd/nohup shape at both request kinds.
    test_repair_is_single_flight(tmp_path)


def test_response_ledger_keeps_all_raw_and_one_accepted_response(tmp_path):
    call_dir = tmp_path / "call"
    scope = ProviderAttemptScope(1, "stage", "main", "attempt-01")
    flight = ProviderSingleFlight(
        call_dir=call_dir, scope=scope, config=ProviderLeaseConfig(2, 0.05)
    )
    primary = flight.invoke(
        provider_call=lambda: CompletionResponse("primary", "stop", None, "p1"),
        request_kind="primary",
        prompt_hash="p",
        schema_hash="s",
    )
    repair = flight.invoke(
        provider_call=lambda: CompletionResponse("repair", "stop", None, "r1"),
        request_kind="json_repair",
        prompt_hash="rp",
        schema_hash="s",
    )
    flight.accept(repair)

    assert primary.raw_path.read_text() == "primary"
    assert repair.raw_path.read_text() == "repair"
    events = [
        json.loads(line)
        for line in (call_dir / "provider-response-ledger.jsonl")
        .read_text().splitlines()
    ]
    assert sum(row["event_type"] == "response_persisted" for row in events) == 2
    assert sum(row["event_type"] == "response_accepted" for row in events) == 1
    accepted = json.loads((call_dir / "accepted-response.json").read_text())
    assert accepted["response_id"] == "r1"
    assert not (call_dir / "raw-response.txt").exists()


def test_legacy_raw_files_are_read_without_rewrite(tmp_path):
    call_dir = tmp_path / "call"
    call_dir.mkdir()
    legacy = call_dir / "raw-response.txt"
    legacy.write_text('{"value":"legacy"}', encoding="utf-8")
    before = legacy.read_bytes()
    (call_dir / "prompt.txt").write_text("PROMPT", encoding="utf-8")
    (call_dir / "audit.json").write_text(json.dumps({
        "status": "raw_received",
        "prompt_version": "v1",
        "prompt_path": "prompt.txt",
        "input_ids": ["C001"],
        "raw_response_path": "raw-response.txt",
        "request_attempt_count": 1,
    }), encoding="utf-8")
    provider = FileBlockingProvider(counter=tmp_path / "never")
    result, _ = AuditedJsonCaller(
        provider=provider,  # type: ignore[arg-type]
        repair_provider=provider,  # type: ignore[arg-type]
    ).call(
        call_dir=call_dir,
        prompt="PROMPT",
        prompt_version="v1",
        schema=TinyOutput,
        schema_hint='{"value":"string"}',
        max_tokens=20,
        input_ids=["C001"],
        resume=True,
    )
    assert result.value == "legacy"
    assert legacy.read_bytes() == before
    assert _count(tmp_path / "never") == 0
