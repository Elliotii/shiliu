from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import socket
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from shiliu.domain import PipelineError
from shiliu.llm import CompletionResponse


RequestKind = Literal["primary", "json_repair"]
LEASE_VERSION = "provider-attempt-lease-v1"
LEDGER_VERSION = "provider-response-ledger-v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _write_all(descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(descriptor, view)
        view = view[written:]


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _exclusive_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
        _write_all(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
        _write_all(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    _fsync_directory(path.parent)


@dataclass(frozen=True)
class ProviderLeaseConfig:
    lease_seconds: float = 900.0
    heartbeat_interval_seconds: float = 15.0

    @classmethod
    def from_env(cls) -> "ProviderLeaseConfig":
        lease = float(os.environ.get("SHILIU_PROVIDER_LEASE_SECONDS", "900"))
        heartbeat = float(
            os.environ.get("SHILIU_PROVIDER_HEARTBEAT_SECONDS", "15")
        )
        if lease <= 0 or heartbeat <= 0 or heartbeat >= lease:
            raise ValueError("Provider lease requires 0 < heartbeat < lease")
        return cls(lease_seconds=lease, heartbeat_interval_seconds=heartbeat)


@dataclass(frozen=True)
class ProviderAttemptScope:
    run_id: int
    stage_name: str
    unit_key: str
    attempt_id: str

    @classmethod
    def from_call_dir(cls, call_dir: Path) -> "ProviderAttemptScope":
        attempt_id = call_dir.name
        unit_key = call_dir.parent.name or "main"
        stage_name = call_dir.parent.parent.name or "unknown-stage"
        run_name = call_dir.parent.parent.parent.name
        match = re.fullmatch(r"run-(\d+)", run_name)
        if match:
            run_id = int(match.group(1))
        else:
            run_id = 0
            stage_name = str(call_dir.parent.resolve())
            unit_key = call_dir.name
            attempt_id = "attempt-01"
        return cls(
            run_id=run_id,
            stage_name=stage_name,
            unit_key=unit_key,
            attempt_id=attempt_id,
        )


@dataclass(frozen=True)
class ProviderInvocation:
    response: CompletionResponse
    raw_path: Path
    raw_sha256: str
    request_kind: RequestKind
    attempt_id: str
    owner_id: str | None
    idempotency_key: str
    resumed_from_ledger: bool
    elapsed_seconds: float


class ImmutableResponseLedger:
    def __init__(self, call_dir: Path) -> None:
        self.call_dir = call_dir
        self.ledger_path = call_dir / "provider-response-ledger.jsonl"
        self.lock_path = call_dir / ".provider-response-ledger.lock"
        self.accepted_path = call_dir / "accepted-response.json"

    def _events(self) -> list[dict[str, Any]]:
        self.call_dir.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_SH)
            if not self.ledger_path.is_file():
                return []
            events = []
            for line in self.ledger_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    events.append(json.loads(line))
            return events

    def append(self, event: dict[str, Any]) -> None:
        self.call_dir.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            with self.ledger_path.open("a", encoding="utf-8") as ledger:
                ledger.write(json.dumps(event, ensure_ascii=False) + "\n")
                ledger.flush()
                os.fsync(ledger.fileno())
            _fsync_directory(self.call_dir)

    def find_response(
        self, *, request_kind: RequestKind, attempt_id: str,
    ) -> ProviderInvocation | None:
        rows = [
            event for event in self._events()
            if event.get("event_type") == "response_persisted"
            and event.get("request_kind") == request_kind
            and event.get("attempt_id") == attempt_id
        ]
        for row in reversed(rows):
            raw_path = self.call_dir / str(row["raw_path"])
            if not raw_path.is_file():
                continue
            raw = raw_path.read_bytes()
            if _sha256_bytes(raw) != row.get("raw_sha256"):
                raise PipelineError(
                    "Provider Response Ledger 的 Raw hash 不匹配",
                    code="provider_response_hash_mismatch",
                    retryable=False,
                )
            reasoning_content = None
            if row.get("reasoning_path"):
                reasoning_path = self.call_dir / row["reasoning_path"]
                if not reasoning_path.is_file() or _sha256_bytes(
                    reasoning_path.read_bytes()
                ) != row.get("reasoning_sha256"):
                    raise PipelineError(
                        "Provider Response Ledger 的 Reasoning hash 不匹配",
                        code="provider_response_hash_mismatch",
                        retryable=False,
                    )
                reasoning_content = reasoning_path.read_text(encoding="utf-8")
            return ProviderInvocation(
                response=CompletionResponse(
                    content=raw.decode("utf-8"),
                    finish_reason=row.get("finish_reason"),
                    usage=row.get("usage"),
                    response_id=row.get("response_id"),
                    reasoning_content=reasoning_content,
                ),
                raw_path=raw_path,
                raw_sha256=row["raw_sha256"],
                request_kind=request_kind,
                attempt_id=attempt_id,
                owner_id=row.get("owner_id"),
                idempotency_key=row["request_idempotency_key"],
                resumed_from_ledger=True,
                elapsed_seconds=float(row.get("elapsed_seconds") or 0),
            )
        return None

    def persist_response(
        self,
        *,
        response: CompletionResponse,
        request_kind: RequestKind,
        attempt_id: str,
        owner_id: str,
        idempotency_key: str,
        elapsed_seconds: float,
    ) -> ProviderInvocation:
        response_key = response.response_id or f"sha-{_sha256_text(response.content)[:20]}"
        safe_key = re.sub(r"[^A-Za-z0-9._-]+", "_", response_key)
        relative = Path("responses") / request_kind / f"response-{safe_key}.txt"
        raw_path = self.call_dir / relative
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_bytes = response.content.encode("utf-8")
        try:
            descriptor = os.open(
                raw_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
        except FileExistsError:
            if raw_path.read_bytes() != raw_bytes:
                raise PipelineError(
                    "不可变 Provider Raw 路径发生内容冲突",
                    code="provider_raw_path_conflict",
                    retryable=False,
                )
        else:
            try:
                _write_all(descriptor, raw_bytes)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            _fsync_directory(raw_path.parent)
        raw_sha = _sha256_bytes(raw_bytes)
        reasoning_relative: Path | None = None
        reasoning_sha: str | None = None
        if response.reasoning_content:
            reasoning_relative = (
                Path("responses") / request_kind / f"reasoning-{safe_key}.txt"
            )
            reasoning_path = self.call_dir / reasoning_relative
            reasoning_bytes = response.reasoning_content.encode("utf-8")
            try:
                reasoning_descriptor = os.open(
                    reasoning_path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
            except FileExistsError:
                if reasoning_path.read_bytes() != reasoning_bytes:
                    raise PipelineError(
                        "不可变 Provider Reasoning 路径发生内容冲突",
                        code="provider_raw_path_conflict",
                        retryable=False,
                    )
            else:
                try:
                    _write_all(reasoning_descriptor, reasoning_bytes)
                    os.fsync(reasoning_descriptor)
                finally:
                    os.close(reasoning_descriptor)
                _fsync_directory(reasoning_path.parent)
            reasoning_sha = _sha256_bytes(reasoning_bytes)
        event = {
            "version": LEDGER_VERSION,
            "event_type": "response_persisted",
            "recorded_at": _utc_now(),
            "response_id": response.response_id,
            "request_kind": request_kind,
            "attempt_id": attempt_id,
            "owner_id": owner_id,
            "request_idempotency_key": idempotency_key,
            "raw_path": str(relative),
            "raw_sha256": raw_sha,
            "reasoning_path": (
                str(reasoning_relative) if reasoning_relative else None
            ),
            "reasoning_sha256": reasoning_sha,
            "usage": response.usage,
            "elapsed_seconds": round(elapsed_seconds, 3),
            "finish_reason": response.finish_reason,
            "accepted": False,
        }
        self.append(event)
        return ProviderInvocation(
            response=response,
            raw_path=raw_path,
            raw_sha256=raw_sha,
            request_kind=request_kind,
            attempt_id=attempt_id,
            owner_id=owner_id,
            idempotency_key=idempotency_key,
            resumed_from_ledger=False,
            elapsed_seconds=round(elapsed_seconds, 3),
        )

    def accept(self, invocation: ProviderInvocation) -> None:
        pointer = {
            "version": "accepted-provider-response-v1",
            "response_id": invocation.response.response_id,
            "request_kind": invocation.request_kind,
            "attempt_id": invocation.attempt_id,
            "raw_path": str(invocation.raw_path.relative_to(self.call_dir)),
            "raw_sha256": invocation.raw_sha256,
            "accepted_at": _utc_now(),
        }
        if self.accepted_path.exists():
            existing = json.loads(self.accepted_path.read_text(encoding="utf-8"))
            if (
                existing.get("raw_path") != pointer["raw_path"]
                or existing.get("raw_sha256") != pointer["raw_sha256"]
            ):
                raise PipelineError(
                    "同一 Attempt 出现多个 accepted Provider Response",
                    code="multiple_accepted_provider_responses",
                    retryable=False,
                )
            return
        try:
            _exclusive_json(self.accepted_path, pointer)
        except FileExistsError:
            existing = json.loads(self.accepted_path.read_text(encoding="utf-8"))
            if (
                existing.get("raw_path") != pointer["raw_path"]
                or existing.get("raw_sha256") != pointer["raw_sha256"]
            ):
                raise PipelineError(
                    "同一 Attempt 出现多个 accepted Provider Response",
                    code="multiple_accepted_provider_responses",
                    retryable=False,
                )
            return
        self.append({
            "version": LEDGER_VERSION,
            "event_type": "response_accepted",
            "recorded_at": _utc_now(),
            **pointer,
            "accepted": True,
        })


class ProviderAttemptLease:
    def __init__(
        self,
        *,
        call_dir: Path,
        scope: ProviderAttemptScope,
        request_kind: RequestKind,
        prompt_hash: str,
        schema_hash: str,
        config: ProviderLeaseConfig,
    ) -> None:
        self.call_dir = call_dir
        self.scope = scope
        self.request_kind = request_kind
        self.prompt_hash = prompt_hash
        self.schema_hash = schema_hash
        self.config = config
        self.owner_id = uuid.uuid4().hex
        self.hostname = socket.gethostname()
        self.lease_path = call_dir / "leases" / f"{request_kind}.json"
        self.takeover_path = call_dir / "leases" / f"{request_kind}.takeover.json"
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self.idempotency_key = _sha256_text("\0".join([
            str(scope.run_id), scope.stage_name, scope.unit_key,
            scope.attempt_id, request_kind, prompt_hash, schema_hash,
        ]))

    def _expires_at(self) -> str:
        return (
            datetime.now(timezone.utc)
            + timedelta(seconds=self.config.lease_seconds)
        ).isoformat(timespec="milliseconds")

    def _new_payload(self) -> dict[str, Any]:
        now = _utc_now()
        return {
            "version": LEASE_VERSION,
            "run_id": self.scope.run_id,
            "stage_name": self.scope.stage_name,
            "unit_key": self.scope.unit_key,
            "attempt_id": self.scope.attempt_id,
            "request_kind": self.request_kind,
            "state": "prepared",
            "owner_id": self.owner_id,
            "pid": os.getpid(),
            "hostname": self.hostname,
            "acquired_at": now,
            "heartbeat_at": now,
            "lease_expires_at": self._expires_at(),
            "request_idempotency_key": self.idempotency_key,
            "prompt_hash": self.prompt_hash,
            "schema_hash": self.schema_hash,
            "provider_request_started_at": None,
            "provider_response_received_at": None,
            "raw_response_path": None,
            "response_id": None,
            "release_reason": None,
        }

    def _read(self) -> dict[str, Any]:
        return json.loads(self.lease_path.read_text(encoding="utf-8"))

    def _owner_alive(self, lease: dict[str, Any]) -> bool | None:
        pid = lease.get("pid")
        hostname = lease.get("hostname")
        if not isinstance(pid, int) or not hostname:
            return None
        if hostname != self.hostname:
            return None
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def acquire(self, ledger: ImmutableResponseLedger) -> None:
        existing_response = ledger.find_response(
            request_kind=self.request_kind,
            attempt_id=self.scope.attempt_id,
        )
        if existing_response is not None:
            return
        payload = self._new_payload()
        try:
            _exclusive_json(self.lease_path, payload)
            return
        except FileExistsError:
            pass
        lease = self._read()
        existing_response = ledger.find_response(
            request_kind=self.request_kind,
            attempt_id=self.scope.attempt_id,
        )
        if existing_response is not None:
            return
        if lease.get("state") in {"failed", "validation_failed", "abandoned"}:
            raise PipelineError(
                "Provider Attempt 已终止；必须创建新 Attempt",
                code="provider_attempt_failed_new_attempt_required",
                retryable=True,
            )
        expires = _parse_time(str(lease["lease_expires_at"]))
        if expires > datetime.now(timezone.utc):
            raise PipelineError(
                "同一 Provider Attempt 正在执行",
                code="provider_already_in_progress",
                retryable=True,
            )
        owner_alive = self._owner_alive(lease)
        if owner_alive is not False:
            raise PipelineError(
                "Provider Lease 已过期但 Owner 未确认死亡，保守拒绝重发",
                code="provider_lease_owner_unconfirmed",
                retryable=True,
            )
        if (
            lease.get("raw_response_path")
            or lease.get("provider_response_received_at")
            or lease.get("state") in {"response_received", "persisted", "completed"}
        ):
            raise PipelineError(
                "Provider Lease 有响应标记但 Ledger 不完整，禁止重发",
                code="provider_response_marker_without_ledger",
                retryable=False,
            )
        takeover = {
            "version": "provider-attempt-takeover-v1",
            "old_owner_id": lease.get("owner_id"),
            "new_owner_id": self.owner_id,
            "taken_over_at": _utc_now(),
        }
        try:
            _exclusive_json(self.takeover_path, takeover)
        except FileExistsError as exc:
            raise PipelineError(
                "Provider Attempt 已由另一个恢复进程接管",
                code="provider_already_in_progress",
                retryable=True,
            ) from exc
        lease.update(
            state="abandoned",
            release_reason="expired_owner_dead_no_response",
            abandoned_at=_utc_now(),
            takeover_owner_id=self.owner_id,
        )
        _atomic_json(self.lease_path, lease)
        _atomic_json(self.call_dir / "attempt-abandoned.json", {
            "version": "provider-attempt-abandoned-v1",
            "attempt_id": self.scope.attempt_id,
            "request_kind": self.request_kind,
            "reason": "expired_owner_dead_no_response",
            "lease_path": str(self.lease_path.relative_to(self.call_dir)),
            "recorded_at": _utc_now(),
        })
        raise PipelineError(
            "旧 Provider Attempt 已标记 abandoned；必须创建新 Attempt",
            code="provider_attempt_abandoned_new_attempt_required",
            retryable=True,
        )

    def _update(self, **changes: Any) -> dict[str, Any]:
        lease = self._read()
        if lease.get("owner_id") != self.owner_id:
            raise PipelineError(
                "Provider Lease Owner 已改变",
                code="provider_lease_ownership_lost",
                retryable=False,
            )
        lease.update(changes, heartbeat_at=_utc_now())
        if lease.get("state") in {"requesting", "repair_requesting"}:
            lease["lease_expires_at"] = self._expires_at()
        _atomic_json(self.lease_path, lease)
        return lease

    def start_heartbeat(self) -> None:
        def heartbeat() -> None:
            while not self._heartbeat_stop.wait(
                self.config.heartbeat_interval_seconds
            ):
                try:
                    self._update()
                except (OSError, ValueError, PipelineError):
                    return

        self._heartbeat_thread = threading.Thread(
            target=heartbeat,
            name=f"provider-lease-{self.request_kind}",
            daemon=True,
        )
        self._heartbeat_thread.start()

    def stop_heartbeat(self) -> None:
        self._heartbeat_stop.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=max(1.0, self.config.heartbeat_interval_seconds * 2))


class ProviderSingleFlight:
    def __init__(
        self,
        *,
        call_dir: Path,
        scope: ProviderAttemptScope | None = None,
        config: ProviderLeaseConfig | None = None,
    ) -> None:
        self.call_dir = call_dir
        self.scope = scope or ProviderAttemptScope.from_call_dir(call_dir)
        self.config = config or ProviderLeaseConfig.from_env()
        self.ledger = ImmutableResponseLedger(call_dir)

    def invoke(
        self,
        *,
        provider_call: Callable[[], CompletionResponse],
        request_kind: RequestKind,
        prompt_hash: str,
        schema_hash: str,
    ) -> ProviderInvocation:
        existing = self.ledger.find_response(
            request_kind=request_kind,
            attempt_id=self.scope.attempt_id,
        )
        if existing is not None:
            return existing
        lease = ProviderAttemptLease(
            call_dir=self.call_dir,
            scope=self.scope,
            request_kind=request_kind,
            prompt_hash=prompt_hash,
            schema_hash=schema_hash,
            config=self.config,
        )
        lease.acquire(self.ledger)
        existing = self.ledger.find_response(
            request_kind=request_kind,
            attempt_id=self.scope.attempt_id,
        )
        if existing is not None:
            return existing
        lease._update(
            state="repair_requesting" if request_kind == "json_repair" else "requesting",
            provider_request_started_at=_utc_now(),
        )
        lease.start_heartbeat()
        started = time.monotonic()
        try:
            response = provider_call()
        except Exception:
            lease.stop_heartbeat()
            lease._update(state="failed", release_reason="provider_call_failed")
            raise
        elapsed = time.monotonic() - started
        lease.stop_heartbeat()
        lease._update(
            state="response_received",
            provider_response_received_at=_utc_now(),
            response_id=response.response_id,
            release_reason="provider_response_received",
        )
        invocation = self.ledger.persist_response(
            response=response,
            request_kind=request_kind,
            attempt_id=self.scope.attempt_id,
            owner_id=lease.owner_id,
            idempotency_key=lease.idempotency_key,
            elapsed_seconds=elapsed,
        )
        lease._update(
            state="persisted",
            raw_response_path=str(invocation.raw_path.relative_to(self.call_dir)),
            response_id=response.response_id,
            release_reason="raw_response_persisted",
        )
        return invocation

    def mark_validation_failed(self, invocation: ProviderInvocation) -> None:
        self._mark_lease(invocation, state="validation_failed")

    def accept(self, invocation: ProviderInvocation) -> None:
        self.ledger.accept(invocation)
        self._mark_lease(
            invocation, state="completed", release_reason="response_accepted"
        )

    def _mark_lease(self, invocation: ProviderInvocation, **changes: Any) -> None:
        if invocation.owner_id is None:
            return
        lease = ProviderAttemptLease(
            call_dir=self.call_dir,
            scope=self.scope,
            request_kind=invocation.request_kind,
            prompt_hash="",
            schema_hash="",
            config=self.config,
        )
        lease.owner_id = invocation.owner_id
        lease._update(**changes)
