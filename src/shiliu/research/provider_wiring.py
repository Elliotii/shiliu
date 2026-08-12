from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import sqlite3
from typing import Any, Callable, Generic, TypeVar

from pydantic import BaseModel

from shiliu.db import Database
from shiliu.research.errors import (
    ResearchConflict,
    ResearchUnsafeState,
    ResearchValidationError,
    SimulatedCrash,
)
from shiliu.research.service import ResearchTaskService


SchemaT = TypeVar("SchemaT", bound=BaseModel)
ProviderFactory = Callable[[str], object]
FaultInjector = Callable[[str], None]


PROVIDER_ACTION_SCHEMA_VERSION = "v5-a-gate-b-provider-call-v1"
PROVIDER_EFFECT_KIND = "structured_provider_call"
SUPPORTED_ROLES = {
    "query_analysis": ("plan", 1200),
    "agent_action": ("navigation", 1200),
    "grounded_answer": ("provisional_synthesis", 4096),
}


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _id(prefix: str, identity: str) -> str:
    return f"{prefix}_{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:32]}"


def _decimal_text(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000000001")), "f")


@dataclass(frozen=True)
class ProviderPricePolicy:
    provider: str = "deepseek_openai_compatible"
    provider_protocol: str = "openai-compatible"
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-v4-pro"
    input_cache_hit_per_million: Decimal = Decimal("0.003625")
    input_cache_miss_per_million: Decimal = Decimal("0.435")
    output_per_million: Decimal = Decimal("0.87")
    reservation_peak_multiplier: Decimal = Decimal("2")
    reservation_transport_attempts: int = 2
    absolute_max_cost_usd: Decimal = Decimal("0.50")
    input_overhead_token_upper_bound: int = 256
    grounded_thinking_enabled: bool = True
    grounded_reasoning_effort: str | None = "high"

    def expected_identity(self, role: str) -> dict[str, object]:
        if role not in SUPPORTED_ROLES:
            raise ResearchValidationError(f"unsupported provider role: {role}")
        grounded = role == "grounded_answer"
        return {
            "provider_protocol": self.provider_protocol,
            "base_url": self.base_url.rstrip("/"),
            "model": self.model,
            "role": role,
            "thinking_enabled": (
                self.grounded_thinking_enabled if grounded else False
            ),
            "reasoning_effort": (
                self.grounded_reasoning_effort if grounded else None
            ),
        }

    def reservation(
        self,
        *,
        request_bytes: int,
        max_output_tokens: int,
    ) -> tuple[int, Decimal]:
        input_upper_bound = request_bytes + self.input_overhead_token_upper_bound
        base = (
            Decimal(input_upper_bound) * self.input_cache_miss_per_million
            + Decimal(max_output_tokens) * self.output_per_million
        ) / Decimal(1_000_000)
        return (
            input_upper_bound,
            base
            * self.reservation_peak_multiplier
            * Decimal(self.reservation_transport_attempts),
        )

    def actual_cost(
        self,
        *,
        input_tokens: int,
        cached_input_tokens: int,
        output_tokens: int,
        transport_attempts: int,
    ) -> Decimal:
        cache_hit = min(input_tokens, cached_input_tokens)
        cache_miss = input_tokens - cache_hit
        one_attempt = (
            Decimal(cache_hit) * self.input_cache_hit_per_million
            + Decimal(cache_miss) * self.input_cache_miss_per_million
            + Decimal(output_tokens) * self.output_per_million
        ) / Decimal(1_000_000)
        return one_attempt * Decimal(transport_attempts)

    def manifest(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "provider_protocol": self.provider_protocol,
            "base_url": self.base_url,
            "model": self.model,
            "unit": "usd_per_1m_tokens",
            "input_cache_hit": str(self.input_cache_hit_per_million),
            "input_cache_miss": str(self.input_cache_miss_per_million),
            "output": str(self.output_per_million),
            "reservation_peak_multiplier": str(
                self.reservation_peak_multiplier
            ),
            "reservation_transport_attempts": self.reservation_transport_attempts,
            "absolute_max_cost_usd": str(self.absolute_max_cost_usd),
            "grounded_thinking_enabled": self.grounded_thinking_enabled,
            "grounded_reasoning_effort": self.grounded_reasoning_effort,
        }


@dataclass
class ProviderCallContext:
    task_id: str
    attempt_id: str
    owner_id: str
    owner_epoch: int
    expected_state_version: int
    expected_checkpoint_id: str | None
    expected_control_generation: int
    operation_key: str
    max_logical_calls: int | None = None
    max_http_attempts: int | None = None
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    deadline_at: str | None = None
    run_budget: ProviderRunBudgetPolicy | None = None


@dataclass(frozen=True)
class ProviderBudgetSnapshot:
    logical_calls: int
    transport_calls: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    committed_cost_usd: str
    active_reserved_cost_usd: str
    accounted_cost_usd: str


@dataclass(frozen=True)
class ProviderRunBudgetPolicy:
    """Frozen aggregate envelope shared by an exact set of evaluation Tasks."""

    run_id: str
    task_ids: tuple[str, ...]
    started_at: str
    max_logical_calls: int = 17
    max_http_attempts: int = 34
    max_input_tokens: int = 140_000
    max_output_tokens: int = 31_984
    max_wall_seconds: int = 34 * 60
    reserve_stop_usd: Decimal = Decimal("0.40")
    absolute_max_cost_usd: Decimal = Decimal("0.50")

    def __post_init__(self) -> None:
        if not self.run_id.strip() or not self.task_ids:
            raise ResearchValidationError("Provider run budget identity is incomplete")
        if len(set(self.task_ids)) != len(self.task_ids):
            raise ResearchValidationError("Provider run budget task_ids are not unique")
        try:
            started = datetime.fromisoformat(self.started_at)
        except ValueError as exc:
            raise ResearchValidationError(
                "Provider run budget started_at is invalid"
            ) from exc
        if started.tzinfo is None:
            raise ResearchValidationError(
                "Provider run budget started_at must be timezone-aware"
            )
        limits = (
            self.max_logical_calls,
            self.max_http_attempts,
            self.max_input_tokens,
            self.max_output_tokens,
            self.max_wall_seconds,
        )
        if any(value <= 0 for value in limits):
            raise ResearchValidationError("Provider run budget limits must be positive")
        if not Decimal("0") < self.reserve_stop_usd <= self.absolute_max_cost_usd:
            raise ResearchValidationError("Provider run cost limits are invalid")
        if self.absolute_max_cost_usd > Decimal("0.50"):
            raise ResearchValidationError(
                "Provider run absolute cost cap exceeds Gate B authorization"
            )

    def manifest(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "task_ids": sorted(self.task_ids),
            "started_at": _iso(datetime.fromisoformat(self.started_at)),
            "max_logical_calls": self.max_logical_calls,
            "max_http_attempts": self.max_http_attempts,
            "max_input_tokens": self.max_input_tokens,
            "max_output_tokens": self.max_output_tokens,
            "max_wall_seconds": self.max_wall_seconds,
            "reserve_stop_usd": str(self.reserve_stop_usd),
            "absolute_max_cost_usd": str(self.absolute_max_cost_usd),
        }

    @property
    def policy_hash(self) -> str:
        return _hash(self.manifest())

    def evidence_policy_binding(self, *, case_id: str) -> dict[str, object]:
        return {
            "policy_hash": self.policy_hash,
            "case_id": case_id,
            **self.manifest(),
        }


@dataclass(frozen=True)
class ProviderRunBudgetSnapshot:
    task_ids: tuple[str, ...]
    committed_logical_calls: int
    active_logical_reservations: int
    accounted_logical_calls: int
    committed_http_attempts: int
    active_http_attempt_reservations: int
    accounted_http_attempts: int
    committed_input_tokens: int
    active_input_token_reservations: int
    accounted_input_tokens: int
    committed_output_tokens: int
    active_output_token_reservations: int
    accounted_output_tokens: int
    committed_cost_usd: str
    active_reserved_cost_usd: str
    accounted_cost_usd: str


@dataclass(frozen=True)
class _KnownFailureResponse:
    usage: dict[str, Any]
    response_id: str | None
    finish_reason: str | None
    latency_ms: float
    retry_count: int

    @property
    def completion_metadata(self) -> dict[str, Any]:
        return {
            "usage": self.usage,
            "response_id": self.response_id,
            "finish_reason": self.finish_reason,
            "latency_ms": self.latency_ms,
            "retry_count": self.retry_count,
            "content_received": True,
        }


@dataclass(frozen=True)
class DurableStructuredResponse(Generic[SchemaT]):
    output: SchemaT
    finish_reason: str | None
    usage: dict[str, Any]
    response_id: str
    latency_ms: float
    retry_count: int
    receipt_binding: dict[str, Any]
    state_version: int
    deduplicated: bool = False


class ProviderBudgetExceeded(ResearchUnsafeState):
    pass


class ProviderDispatchUnknown(ResearchUnsafeState):
    pass


class ProviderCallFailed(ResearchUnsafeState):
    code = "invalid_model_output"

    def __init__(
        self,
        message: str,
        *,
        completion_metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.completion_metadata = completion_metadata


class ReceiptBoundProviderFactory:
    """Provider factory compatible with the accepted V4 structured-call services."""

    def __init__(
        self,
        *,
        service: ReceiptBoundProviderService,
        context: ProviderCallContext,
        provider_factory: ProviderFactory,
    ) -> None:
        self.service = service
        self.context = context
        self.provider_factory = provider_factory
        self._ordinals: dict[str, int] = {}
        self._receipt_bindings: list[dict[str, Any]] = []

    def __call__(self, role: str) -> ReceiptBoundStructuredProvider:
        if role not in SUPPORTED_ROLES:
            raise ResearchValidationError(f"unsupported provider role: {role}")
        return ReceiptBoundStructuredProvider(factory=self, role=role)

    def _next_operation_key(self, role: str) -> str:
        ordinal = self._ordinals.get(role, 0) + 1
        self._ordinals[role] = ordinal
        return f"{self.context.operation_key}:{role}:{ordinal}"

    @property
    def receipt_bindings(self) -> tuple[dict[str, Any], ...]:
        """Successful durable receipts emitted through this exact factory."""

        return tuple(dict(value) for value in self._receipt_bindings)

    def _record_receipt(self, binding: dict[str, Any]) -> None:
        receipt_hash = str(binding.get("receipt_hash") or "")
        if receipt_hash and not any(
            value.get("receipt_hash") == receipt_hash
            for value in self._receipt_bindings
        ):
            self._receipt_bindings.append(dict(binding))


class ReceiptBoundStructuredProvider:
    def __init__(self, *, factory: ReceiptBoundProviderFactory, role: str) -> None:
        self.factory = factory
        self.role = role

    def generate_structured(
        self,
        *,
        role: str,
        messages: list[dict[str, str]],
        response_schema: type[SchemaT],
        max_tokens: int | None = None,
        timeout_seconds: float | None = None,
    ) -> DurableStructuredResponse[SchemaT]:
        if role != self.role:
            raise ResearchValidationError("provider role does not match factory role")
        response = self.factory.service.execute(
            context=self.factory.context,
            operation_key=self.factory._next_operation_key(role),
            provider_factory=self.factory.provider_factory,
            role=role,
            messages=messages,
            response_schema=response_schema,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
        )
        self.factory.context.expected_state_version = response.state_version
        self.factory._record_receipt(response.receipt_binding)
        return response


class ReceiptBoundProviderService:
    """Durably fences and receipts one structured Provider logical call.

    The service deliberately has no credential loader or network client. A Provider
    factory is invoked only after the durable reservation is in_flight.
    """

    def __init__(
        self,
        *,
        db: Database,
        kernel: ResearchTaskService,
        price_policy: ProviderPricePolicy | None = None,
        fault_injector: FaultInjector | None = None,
        provider_dispatch_authorized: bool = False,
    ) -> None:
        self.db = db
        self.kernel = kernel
        self.price_policy = price_policy or ProviderPricePolicy()
        self.fault_injector = fault_injector or (lambda _point: None)
        self.provider_dispatch_authorized = provider_dispatch_authorized

    def factory(
        self,
        *,
        context: ProviderCallContext,
        provider_factory: ProviderFactory,
    ) -> ReceiptBoundProviderFactory:
        return ReceiptBoundProviderFactory(
            service=self,
            context=context,
            provider_factory=provider_factory,
        )

    def execute(
        self,
        *,
        context: ProviderCallContext,
        operation_key: str,
        provider_factory: ProviderFactory,
        role: str,
        messages: list[dict[str, str]],
        response_schema: type[SchemaT],
        max_tokens: int | None = None,
        timeout_seconds: float | None = None,
    ) -> DurableStructuredResponse[SchemaT]:
        if not self.provider_dispatch_authorized:
            raise ResearchUnsafeState(
                "Provider dispatch is disabled until an explicit run authorization"
            )
        if role not in SUPPORTED_ROLES:
            raise ResearchValidationError(f"unsupported provider role: {role}")
        action_kind, role_cap = SUPPORTED_ROLES[role]
        requested_max = role_cap if max_tokens is None else int(max_tokens)
        if requested_max <= 0 or requested_max > role_cap:
            raise ResearchValidationError(
                f"{role} max_tokens exceeds server cap {role_cap}"
            )
        schema_json = response_schema.model_json_schema()
        structured_request = {
            "provider": self.price_policy.provider,
            "provider_identity": self.price_policy.expected_identity(role),
            "messages": messages,
            "response_schema": schema_json,
            "max_tokens": requested_max,
            "timeout_seconds": timeout_seconds,
        }
        structured_request_json = _canonical_json(structured_request)
        structured_request_hash = hashlib.sha256(
            structured_request_json.encode("utf-8")
        ).hexdigest()
        input_upper, reservation = self.price_policy.reservation(
            request_bytes=len(structured_request_json.encode("utf-8")),
            max_output_tokens=requested_max,
        )
        descriptor = {
            "wiring_version": PROVIDER_ACTION_SCHEMA_VERSION,
            "provider": self.price_policy.provider,
            "model": self.price_policy.model,
            "role": role,
            "provider_identity": self.price_policy.expected_identity(role),
            "operation_key": operation_key,
            "structured_request_hash": structured_request_hash,
            "response_schema_hash": _hash(schema_json),
            "max_output_tokens": requested_max,
            "input_token_upper_bound": input_upper,
            "worst_case_cost_usd": _decimal_text(reservation),
            "price_table": self.price_policy.manifest(),
            "run_budget_policy_hash": (
                context.run_budget.policy_hash if context.run_budget else None
            ),
            "per_case_budget": {
                "max_logical_calls": context.max_logical_calls,
                "max_http_attempts": context.max_http_attempts,
                "max_input_tokens": context.max_input_tokens,
                "max_output_tokens": context.max_output_tokens,
                "deadline_at": context.deadline_at,
            },
        }
        descriptor_hash = _hash(descriptor)
        terminal_command_id = f"provider:{operation_key}:terminal"
        replay = self._terminal_replay(
            context=context,
            command_id=terminal_command_id,
            payload_hash=descriptor_hash,
            response_schema=response_schema,
        )
        if replay is not None:
            return replay
        self._assert_call_caps(
            context,
            requested_input_tokens=input_upper,
            requested_output_tokens=requested_max,
        )
        side_effect_id, state_version = self._reserve(
            context=context,
            operation_key=operation_key,
            descriptor=descriptor,
            descriptor_hash=descriptor_hash,
            terminal_command_id=terminal_command_id,
            reservation=reservation,
        )
        context.expected_state_version = state_version
        state_version = self._start(
            context=context,
            operation_key=operation_key,
            side_effect_id=side_effect_id,
            descriptor_hash=descriptor_hash,
        )
        context.expected_state_version = state_version
        self.fault_injector("before_provider_factory")
        try:
            provider = provider_factory(role)
        except SimulatedCrash:
            raise
        except Exception as exc:
            state_version = self._mark_unknown(
                context=context,
                operation_key=operation_key,
                side_effect_id=side_effect_id,
                descriptor=descriptor,
                descriptor_hash=descriptor_hash,
                terminal_command_id=terminal_command_id,
                reason=f"{type(exc).__name__}: {exc}"[:500],
            )
            context.expected_state_version = state_version
            raise ProviderDispatchUnknown(
                "Provider factory outcome is unknown; automatic replay is forbidden"
            ) from exc
        actual_identity = self._actual_provider_identity(provider, role)
        identity_mismatches = self._identity_mismatches(
            expected=descriptor["provider_identity"],
            actual=actual_identity,
        )
        if identity_mismatches:
            state_version = self._reject_identity(
                context=context,
                operation_key=operation_key,
                side_effect_id=side_effect_id,
                descriptor=descriptor,
                descriptor_hash=descriptor_hash,
                terminal_command_id=terminal_command_id,
                actual_identity=actual_identity,
                mismatches=identity_mismatches,
            )
            context.expected_state_version = state_version
            raise ProviderCallFailed(
                "Provider runtime identity does not match the authorized identity"
            )
        try:
            raw = provider.generate_structured(  # type: ignore[attr-defined]
                role=role,
                messages=messages,
                response_schema=response_schema,
                max_tokens=requested_max,
                timeout_seconds=timeout_seconds,
            )
            self.fault_injector("after_provider_dispatch")
        except SimulatedCrash:
            raise
        except Exception as exc:
            known_failure = self._known_failure_response(exc)
            if known_failure is not None:
                if not self._has_operation_id(known_failure.response_id):
                    state_version = self._mark_unknown(
                        context=context,
                        operation_key=operation_key,
                        side_effect_id=side_effect_id,
                        descriptor=descriptor,
                        descriptor_hash=descriptor_hash,
                        terminal_command_id=terminal_command_id,
                        reason="Provider result has no response/operation ID",
                    )
                    context.expected_state_version = state_version
                    raise ProviderDispatchUnknown(
                        "Provider operation identity is missing; replay is forbidden"
                    ) from exc
                state_version = self._finish_failed(
                    context=context,
                    operation_key=operation_key,
                    action_kind=action_kind,
                    side_effect_id=side_effect_id,
                    descriptor=descriptor,
                    descriptor_hash=descriptor_hash,
                    terminal_command_id=terminal_command_id,
                    raw=known_failure,
                    reason=f"{type(exc).__name__}: {exc}"[:500],
                )
                context.expected_state_version = state_version
                raise ProviderCallFailed(
                    "Provider returned a known invalid structured result",
                    completion_metadata=known_failure.completion_metadata,
                ) from exc
            state_version = self._mark_unknown(
                context=context,
                operation_key=operation_key,
                side_effect_id=side_effect_id,
                descriptor=descriptor,
                descriptor_hash=descriptor_hash,
                terminal_command_id=terminal_command_id,
                reason=f"{type(exc).__name__}: {exc}"[:500],
            )
            context.expected_state_version = state_version
            raise ProviderDispatchUnknown(
                "Provider dispatch outcome is unknown; automatic replay is forbidden"
            ) from exc
        raw_output = getattr(raw, "output", raw)
        try:
            output = (
                raw_output
                if isinstance(raw_output, response_schema)
                else response_schema.model_validate(raw_output)
            )
            output_payload = output.model_dump(mode="json")
        except Exception as exc:
            try:
                self._normalize_usage(getattr(raw, "usage", None))
            except Exception:
                state_version = self._mark_unknown(
                    context=context,
                    operation_key=operation_key,
                    side_effect_id=side_effect_id,
                    descriptor=descriptor,
                    descriptor_hash=descriptor_hash,
                    terminal_command_id=terminal_command_id,
                    reason="Provider result has no accountable usage",
                )
                context.expected_state_version = state_version
                raise ProviderDispatchUnknown(
                    "Provider usage cannot be receipted; replay is forbidden"
                ) from exc
            if not self._has_operation_id(getattr(raw, "response_id", None)):
                state_version = self._mark_unknown(
                    context=context,
                    operation_key=operation_key,
                    side_effect_id=side_effect_id,
                    descriptor=descriptor,
                    descriptor_hash=descriptor_hash,
                    terminal_command_id=terminal_command_id,
                    reason="Provider result has no response/operation ID",
                )
                context.expected_state_version = state_version
                raise ProviderDispatchUnknown(
                    "Provider operation identity is missing; replay is forbidden"
                ) from exc
            state_version = self._finish_failed(
                context=context,
                operation_key=operation_key,
                action_kind=action_kind,
                side_effect_id=side_effect_id,
                descriptor=descriptor,
                descriptor_hash=descriptor_hash,
                terminal_command_id=terminal_command_id,
                raw=raw,
                reason=f"{type(exc).__name__}: {exc}"[:500],
            )
            context.expected_state_version = state_version
            raise ProviderCallFailed(
                "Provider response could not be durably validated",
                completion_metadata=self._completion_metadata(raw),
            ) from exc
        try:
            usage = self._normalize_usage(getattr(raw, "usage", None))
        except Exception as exc:
            state_version = self._mark_unknown(
                context=context,
                operation_key=operation_key,
                side_effect_id=side_effect_id,
                descriptor=descriptor,
                descriptor_hash=descriptor_hash,
                terminal_command_id=terminal_command_id,
                reason="Provider result has no accountable usage",
            )
            context.expected_state_version = state_version
            raise ProviderDispatchUnknown(
                "Provider usage cannot be receipted; replay is forbidden"
            ) from exc
        if (
            usage["input_tokens"] > int(descriptor["input_token_upper_bound"])
            or usage["output_tokens"] > int(descriptor["max_output_tokens"])
        ):
            state_version = self._mark_unknown(
                context=context,
                operation_key=operation_key,
                side_effect_id=side_effect_id,
                descriptor=descriptor,
                descriptor_hash=descriptor_hash,
                terminal_command_id=terminal_command_id,
                reason="Provider usage exceeded the pre-call token reservation",
            )
            context.expected_state_version = state_version
            raise ProviderDispatchUnknown(
                "Provider usage exceeded its durable reservation; replay is forbidden"
            )
        if not self._has_operation_id(getattr(raw, "response_id", None)):
            state_version = self._mark_unknown(
                context=context,
                operation_key=operation_key,
                side_effect_id=side_effect_id,
                descriptor=descriptor,
                descriptor_hash=descriptor_hash,
                terminal_command_id=terminal_command_id,
                reason="Provider result has no response/operation ID",
            )
            context.expected_state_version = state_version
            raise ProviderDispatchUnknown(
                "Provider operation identity is missing; replay is forbidden"
            )
        response = self._finish_succeeded(
            context=context,
            operation_key=operation_key,
            action_kind=action_kind,
            side_effect_id=side_effect_id,
            descriptor=descriptor,
            descriptor_hash=descriptor_hash,
            terminal_command_id=terminal_command_id,
            raw=raw,
            output_payload=output_payload,
            usage=usage,
            response_schema=response_schema,
        )
        context.expected_state_version = response.state_version
        return response

    def budget_snapshot(self, task_id: str) -> ProviderBudgetSnapshot:
        with self.db.connect() as connection:
            return self._budget_snapshot(connection, task_id)

    def run_budget_snapshot(
        self, policy: ProviderRunBudgetPolicy
    ) -> ProviderRunBudgetSnapshot:
        with self.db.connect() as connection:
            self._assert_run_budget_binding(connection, policy)
            return self._run_budget_snapshot(connection, policy.task_ids)

    def _terminal_replay(
        self,
        *,
        context: ProviderCallContext,
        command_id: str,
        payload_hash: str,
        response_schema: type[SchemaT],
    ) -> DurableStructuredResponse[SchemaT] | None:
        with self.kernel._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM research_command_receipts WHERE task_id=? AND command_id=?",
                (context.task_id, command_id),
            ).fetchone()
            if row is None:
                return None
            task = self.kernel._task(connection, context.task_id)
            self.kernel._assert_owner(
                task,
                owner_id=context.owner_id,
                owner_epoch=context.owner_epoch,
                now=self.kernel._now(),
            )
            self._assert_control(task, context.expected_control_generation)
            if str(row["payload_hash"]) != payload_hash:
                self.kernel._existing_receipt(
                    connection,
                    task_id=context.task_id,
                    command_id=command_id,
                    payload_hash=payload_hash,
                )
                raise AssertionError("unreachable")
            payload = json.loads(str(row["response_json"]))
            payload["state_version"] = int(task["state_version"])
        status = str(payload.get("status"))
        if status == "budget_rejected":
            raise ProviderBudgetExceeded(str(payload["error"]))
        if status == "unknown":
            raise ProviderDispatchUnknown(str(payload["error"]))
        if status == "failed":
            raise ProviderCallFailed(
                str(payload["error"]),
                completion_metadata=payload.get("completion_metadata"),
            )
        return self._response_from_payload(
            payload, response_schema=response_schema, deduplicated=True
        )

    def _reserve(
        self,
        *,
        context: ProviderCallContext,
        operation_key: str,
        descriptor: dict[str, Any],
        descriptor_hash: str,
        terminal_command_id: str,
        reservation: Decimal,
    ) -> tuple[str, int]:
        now_value = self.kernel._now()
        now = _iso(now_value)
        rejection: str | None = None
        with self.kernel._transaction() as connection:
            task, attempt = self._guard(
                connection, context=context, expected_state=True, now=now_value
            )
            existing = connection.execute(
                """
                SELECT * FROM research_side_effects
                WHERE task_id=? AND effect_kind=? AND idempotency_key=?
                """,
                (context.task_id, PROVIDER_EFFECT_KIND, operation_key),
            ).fetchone()
            if existing is not None:
                if str(existing["request_hash"]) != descriptor_hash:
                    raise ResearchUnsafeState(
                        "provider operation key request hash mismatch"
                    )
                status = str(existing["status"])
                if status != "reserved":
                    raise ProviderDispatchUnknown(
                        f"Provider SideEffect is {status}; automatic replay is forbidden"
                    )
                if int(existing["owner_epoch"]) != context.owner_epoch:
                    raise ResearchConflict("Provider SideEffect stale owner fence")
                return str(existing["side_effect_id"]), int(task["state_version"])
            unresolved = int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM research_side_effects
                    WHERE task_id=? AND status IN ('in_flight', 'unknown')
                    """,
                    (context.task_id,),
                ).fetchone()[0]
            )
            if unresolved:
                raise ProviderDispatchUnknown(
                    "unresolved SideEffect blocks every new Provider dispatch"
                )
            budget = self._budget_snapshot(connection, context.task_id)
            projected = Decimal(budget.accounted_cost_usd) + reservation
            rejection_detail = self._budget_rejection(
                connection,
                context=context,
                descriptor=descriptor,
                reservation=reservation,
                now=now_value,
            )
            if projected > self.price_policy.absolute_max_cost_usd:
                error = (
                    "pre-call worst-case reservation would exceed absolute cost cap: "
                    f"{_decimal_text(projected)} > "
                    f"{self.price_policy.absolute_max_cost_usd}"
                )
            elif rejection_detail is not None:
                error = rejection_detail
            else:
                error = None
            if error is not None:
                self.kernel._event(
                    connection,
                    task_id=context.task_id,
                    goal_id=str(attempt["goal_id"]),
                    attempt_id=context.attempt_id,
                    event_type="provider_cost_reservation_rejected",
                    payload={
                        "operation_key": operation_key,
                        "role": descriptor["role"],
                        "accounted_cost_usd": budget.accounted_cost_usd,
                        "requested_reservation_usd": _decimal_text(reservation),
                        "absolute_max_cost_usd": str(
                            self.price_policy.absolute_max_cost_usd
                        ),
                        "run_budget_policy_hash": descriptor.get(
                            "run_budget_policy_hash"
                        ),
                    },
                    command_id=terminal_command_id,
                    owner_epoch=context.owner_epoch,
                    now=now,
                )
                response = {"status": "budget_rejected", "error": error}
                self.kernel._insert_receipt(
                    connection,
                    task_id=context.task_id,
                    command_id=terminal_command_id,
                    command_type="provider_call_budget_rejected",
                    payload_hash=descriptor_hash,
                    outcome_reference=None,
                    response=response,
                    owner_epoch=context.owner_epoch,
                    now=now,
                )
                rejection = error
            else:
                side_effect_id = _id("effect", f"{context.task_id}:{operation_key}")
                connection.execute(
                    """
                    INSERT INTO research_side_effects(
                        side_effect_id, task_id, attempt_id, command_id,
                        idempotency_key, effect_kind, request_hash, request_json,
                        status, owner_epoch, provider_operation_id, receipt_hash,
                        result_reference, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, 'reserved', ?, NULL, NULL,
                             NULL, ?, ?)
                    """,
                    (
                        side_effect_id,
                        context.task_id,
                        context.attempt_id,
                        f"provider:{operation_key}:reserve",
                        operation_key,
                        PROVIDER_EFFECT_KIND,
                        descriptor_hash,
                        _canonical_json(descriptor),
                        context.owner_epoch,
                        now,
                        now,
                    ),
                )
                connection.execute(
                    "UPDATE research_tasks SET state_version=state_version+1, "
                    "updated_at=? WHERE task_id=?",
                    (now, context.task_id),
                )
                self.kernel._event(
                    connection,
                    task_id=context.task_id,
                    goal_id=str(attempt["goal_id"]),
                    attempt_id=context.attempt_id,
                    event_type="provider_call_reserved",
                    payload={
                        "side_effect_id": side_effect_id,
                        "provider": descriptor["provider"],
                        "model": descriptor["model"],
                        "role": descriptor["role"],
                        "structured_request_hash": descriptor[
                            "structured_request_hash"
                        ],
                        "worst_case_cost_usd": descriptor[
                            "worst_case_cost_usd"
                        ],
                    },
                    command_id=f"provider:{operation_key}:reserve",
                    owner_epoch=context.owner_epoch,
                    now=now,
                )
                self.fault_injector("after_provider_reserve")
                return side_effect_id, int(task["state_version"]) + 1
        assert rejection is not None
        raise ProviderBudgetExceeded(rejection)

    def _start(
        self,
        *,
        context: ProviderCallContext,
        operation_key: str,
        side_effect_id: str,
        descriptor_hash: str,
    ) -> int:
        now_value = self.kernel._now()
        now = _iso(now_value)
        with self.kernel._transaction() as connection:
            task, attempt = self._guard(
                connection, context=context, expected_state=True, now=now_value
            )
            effect = self.kernel._side_effect(connection, side_effect_id)
            if (
                str(effect["request_hash"]) != descriptor_hash
                or str(effect["status"]) != "reserved"
                or int(effect["owner_epoch"]) != context.owner_epoch
            ):
                raise ProviderDispatchUnknown(
                    "Provider SideEffect cannot safely transition to in_flight"
                )
            connection.execute(
                "UPDATE research_side_effects SET status='in_flight', "
                "updated_at=? WHERE side_effect_id=?",
                (now, side_effect_id),
            )
            connection.execute(
                "UPDATE research_tasks SET state_version=state_version+1, "
                "updated_at=? WHERE task_id=?",
                (now, context.task_id),
            )
            self.kernel._event(
                connection,
                task_id=context.task_id,
                goal_id=str(attempt["goal_id"]),
                attempt_id=context.attempt_id,
                event_type="provider_call_in_flight",
                payload={"side_effect_id": side_effect_id},
                command_id=f"provider:{operation_key}:start",
                owner_epoch=context.owner_epoch,
                now=now,
            )
            self.fault_injector("after_provider_in_flight")
            return int(task["state_version"]) + 1

    def _finish_succeeded(
        self,
        *,
        context: ProviderCallContext,
        operation_key: str,
        action_kind: str,
        side_effect_id: str,
        descriptor: dict[str, Any],
        descriptor_hash: str,
        terminal_command_id: str,
        raw: object,
        output_payload: dict[str, Any],
        usage: dict[str, int],
        response_schema: type[SchemaT],
    ) -> DurableStructuredResponse[SchemaT]:
        metadata = self._response_metadata(raw, usage)
        actual_cost = self.price_policy.actual_cost(
            input_tokens=usage["input_tokens"],
            cached_input_tokens=usage["cached_input_tokens"],
            output_tokens=usage["output_tokens"],
            transport_attempts=metadata["transport_attempts"],
        )
        reservation = Decimal(str(descriptor["worst_case_cost_usd"]))
        if actual_cost > reservation:
            state_version = self._mark_unknown(
                context=context,
                operation_key=operation_key,
                side_effect_id=side_effect_id,
                descriptor=descriptor,
                descriptor_hash=descriptor_hash,
                terminal_command_id=terminal_command_id,
                reason="actual Provider cost exceeded its pre-call reservation",
            )
            context.expected_state_version = state_version
            raise ProviderDispatchUnknown(
                "Provider cost receipt exceeded reservation; replay is forbidden"
            )
        output_hash = _hash(output_payload)
        operation_id = str(metadata["response_id"])
        result_reference = _id(
            "provider_result",
            f"{descriptor['structured_request_hash']}:{output_hash}:{operation_id}",
        )
        binding = {
            "provider": descriptor["provider"],
            "model": descriptor["model"],
            "role": descriptor["role"],
            "provider_identity": descriptor["provider_identity"],
            "structured_request_hash": descriptor["structured_request_hash"],
            "response_schema_hash": descriptor["response_schema_hash"],
            "usage": usage,
            "cost_usd": _decimal_text(actual_cost),
            "provider_operation_id": operation_id,
            "result_reference": result_reference,
            "output_hash": output_hash,
            "transport_attempts": metadata["transport_attempts"],
        }
        receipt_hash = _hash(binding)
        binding["receipt_hash"] = receipt_hash
        now_value = self.kernel._now()
        now = _iso(now_value)
        with self.kernel._transaction() as connection:
            task, attempt = self._guard(
                connection, context=context, expected_state=True, now=now_value
            )
            effect = self.kernel._side_effect(connection, side_effect_id)
            self._assert_in_flight(effect, context, descriptor_hash)
            action_id = _id("inner_action", f"{context.task_id}:{operation_key}")
            observation = {
                "provider_call": binding,
                "output": output_payload,
                "finish_reason": metadata["finish_reason"],
                "latency_ms": metadata["latency_ms"],
                "retry_count": metadata["retry_count"],
                "reservation_usd": descriptor["worst_case_cost_usd"],
            }
            self._insert_action(
                connection,
                action_id=action_id,
                action_kind=action_kind,
                operation_key=operation_key,
                context=context,
                attempt=attempt,
                side_effect_id=side_effect_id,
                descriptor=descriptor,
                status="succeeded",
                observation=observation,
                now=now,
            )
            connection.execute(
                """
                UPDATE research_side_effects
                SET status='succeeded', provider_operation_id=?, receipt_hash=?,
                    result_reference=?, updated_at=?
                WHERE side_effect_id=?
                """,
                (operation_id, receipt_hash, result_reference, now, side_effect_id),
            )
            connection.execute(
                "UPDATE research_tasks SET state_version=state_version+1, "
                "updated_at=? WHERE task_id=?",
                (now, context.task_id),
            )
            next_version = int(task["state_version"]) + 1
            response_payload = {
                "status": "succeeded",
                "output": output_payload,
                "finish_reason": metadata["finish_reason"],
                "usage": usage,
                "response_id": operation_id,
                "latency_ms": metadata["latency_ms"],
                "retry_count": metadata["retry_count"],
                "receipt_binding": binding,
                "state_version": next_version,
            }
            self.kernel._event(
                connection,
                task_id=context.task_id,
                goal_id=str(attempt["goal_id"]),
                attempt_id=context.attempt_id,
                event_type="provider_call_receipted",
                payload={
                    "side_effect_id": side_effect_id,
                    "action_id": action_id,
                    **binding,
                },
                command_id=terminal_command_id,
                owner_epoch=context.owner_epoch,
                now=now,
            )
            self.kernel._insert_receipt(
                connection,
                task_id=context.task_id,
                command_id=terminal_command_id,
                command_type="provider_call_receipted",
                payload_hash=descriptor_hash,
                outcome_reference=result_reference,
                response=response_payload,
                owner_epoch=context.owner_epoch,
                now=now,
            )
            self.fault_injector("after_provider_receipt")
        return self._response_from_payload(
            response_payload,
            response_schema=response_schema,
            deduplicated=False,
        )

    def _assert_call_caps(
        self,
        context: ProviderCallContext,
        *,
        requested_input_tokens: int,
        requested_output_tokens: int,
    ) -> None:
        if (
            context.max_logical_calls is None
            and context.max_http_attempts is None
            and context.max_input_tokens is None
            and context.max_output_tokens is None
            and context.deadline_at is None
        ):
            return
        snapshot = self.budget_snapshot(context.task_id)
        if (
            context.max_logical_calls is not None
            and snapshot.logical_calls >= context.max_logical_calls
        ):
            raise ProviderBudgetExceeded(
                "Provider product logical-call cap is exhausted"
            )
        if context.max_http_attempts is not None:
            worst_transport = (
                snapshot.transport_calls
                + self.price_policy.reservation_transport_attempts
            )
            if worst_transport > context.max_http_attempts:
                raise ProviderBudgetExceeded(
                    "Provider product HTTP-attempt reservation exceeds its cap"
                )
        if (
            context.max_input_tokens is not None
            and snapshot.input_tokens + requested_input_tokens
            > context.max_input_tokens
        ):
            raise ProviderBudgetExceeded(
                "Provider product input-token reservation exceeds its cap"
            )
        if (
            context.max_output_tokens is not None
            and snapshot.output_tokens + requested_output_tokens
            > context.max_output_tokens
        ):
            raise ProviderBudgetExceeded(
                "Provider product output-token reservation exceeds its cap"
            )
        if context.deadline_at is not None:
            deadline = datetime.fromisoformat(context.deadline_at)
            if deadline.tzinfo is None:
                raise ResearchValidationError(
                    "Provider product deadline must be timezone-aware"
                )
            if self.kernel._now() >= deadline:
                raise ProviderBudgetExceeded(
                    "Provider product wall-time cap is exhausted"
                )

    def _budget_rejection(
        self,
        connection: sqlite3.Connection,
        *,
        context: ProviderCallContext,
        descriptor: dict[str, Any],
        reservation: Decimal,
        now: datetime,
    ) -> str | None:
        """Repeat all per-case/run-wide gates under the reservation write lock."""

        task_snapshot = self._run_budget_snapshot(connection, (context.task_id,))
        requested_input = int(descriptor["input_token_upper_bound"])
        requested_output = int(descriptor["max_output_tokens"])
        requested_http = self.price_policy.reservation_transport_attempts
        per_case_checks = (
            (
                context.max_logical_calls,
                task_snapshot.accounted_logical_calls + 1,
                "logical-call",
            ),
            (
                context.max_http_attempts,
                task_snapshot.accounted_http_attempts + requested_http,
                "HTTP-attempt",
            ),
            (
                context.max_input_tokens,
                task_snapshot.accounted_input_tokens + requested_input,
                "input-token",
            ),
            (
                context.max_output_tokens,
                task_snapshot.accounted_output_tokens + requested_output,
                "output-token",
            ),
        )
        for limit, projected, name in per_case_checks:
            if limit is not None and projected > limit:
                return (
                    f"Provider product {name} reservation exceeds its cap: "
                    f"{projected} > {limit}"
                )
        if context.deadline_at is not None:
            deadline = datetime.fromisoformat(context.deadline_at)
            if deadline.tzinfo is None:
                return "Provider product deadline is not timezone-aware"
            if now >= deadline:
                return "Provider product wall-time cap is exhausted"

        policy = context.run_budget
        if policy is None:
            return None
        self._assert_run_budget_binding(connection, policy)
        if context.task_id not in policy.task_ids:
            return "Provider Task is outside the frozen run-wide budget membership"
        run_snapshot = self._run_budget_snapshot(connection, policy.task_ids)
        started = datetime.fromisoformat(policy.started_at).astimezone(timezone.utc)
        elapsed = (now.astimezone(timezone.utc) - started).total_seconds()
        if elapsed < 0:
            return "Provider run budget started_at is in the future"
        run_checks = (
            (
                policy.max_logical_calls,
                run_snapshot.accounted_logical_calls + 1,
                "logical-call",
            ),
            (
                policy.max_http_attempts,
                run_snapshot.accounted_http_attempts + requested_http,
                "HTTP-attempt",
            ),
            (
                policy.max_input_tokens,
                run_snapshot.accounted_input_tokens + requested_input,
                "input-token",
            ),
            (
                policy.max_output_tokens,
                run_snapshot.accounted_output_tokens + requested_output,
                "output-token",
            ),
        )
        for limit, projected, name in run_checks:
            if projected > limit:
                return (
                    f"Provider run-wide {name} reservation exceeds its cap: "
                    f"{projected} > {limit}"
                )
        if elapsed >= policy.max_wall_seconds:
            return "Provider run-wide wall-time cap is exhausted"
        accounted = Decimal(run_snapshot.accounted_cost_usd)
        if accounted >= policy.reserve_stop_usd:
            return (
                "Provider run-wide reserve-stop threshold is exhausted: "
                f"{_decimal_text(accounted)} >= {policy.reserve_stop_usd}"
            )
        projected_cost = accounted + reservation
        if projected_cost > policy.absolute_max_cost_usd:
            return (
                "Provider run-wide worst-case cost reservation exceeds its cap: "
                f"{_decimal_text(projected_cost)} > "
                f"{policy.absolute_max_cost_usd}"
            )
        return None

    def _finish_failed(
        self,
        *,
        context: ProviderCallContext,
        operation_key: str,
        action_kind: str,
        side_effect_id: str,
        descriptor: dict[str, Any],
        descriptor_hash: str,
        terminal_command_id: str,
        raw: object,
        reason: str,
    ) -> int:
        usage_raw = getattr(raw, "usage", None)
        usage = self._normalize_usage(usage_raw)
        metadata = self._response_metadata(raw, usage)
        actual_cost = self.price_policy.actual_cost(
            input_tokens=usage["input_tokens"],
            cached_input_tokens=usage["cached_input_tokens"],
            output_tokens=usage["output_tokens"],
            transport_attempts=metadata["transport_attempts"],
        )
        result_reference = _id(
            "provider_result", f"{descriptor_hash}:invalid:{metadata['response_id']}"
        )
        binding = {
            "provider": descriptor["provider"],
            "model": descriptor["model"],
            "role": descriptor["role"],
            "provider_identity": descriptor["provider_identity"],
            "structured_request_hash": descriptor["structured_request_hash"],
            "response_schema_hash": descriptor["response_schema_hash"],
            "usage": usage,
            "cost_usd": _decimal_text(actual_cost),
            "provider_operation_id": metadata["response_id"],
            "result_reference": result_reference,
            "output_hash": None,
            "transport_attempts": metadata["transport_attempts"],
            "failure": reason,
        }
        receipt_hash = _hash(binding)
        binding["receipt_hash"] = receipt_hash
        now_value = self.kernel._now()
        now = _iso(now_value)
        with self.kernel._transaction() as connection:
            task, attempt = self._guard(
                connection, context=context, expected_state=True, now=now_value
            )
            effect = self.kernel._side_effect(connection, side_effect_id)
            self._assert_in_flight(effect, context, descriptor_hash)
            self._insert_action(
                connection,
                action_id=_id("inner_action", f"{context.task_id}:{operation_key}"),
                action_kind=action_kind,
                operation_key=operation_key,
                context=context,
                attempt=attempt,
                side_effect_id=side_effect_id,
                descriptor=descriptor,
                status="failed",
                observation={"provider_call": binding, "error": reason},
                now=now,
                error_code="provider_output_invalid",
                error_detail=reason,
            )
            connection.execute(
                """
                UPDATE research_side_effects SET status='failed',
                    provider_operation_id=?, receipt_hash=?, result_reference=?,
                    updated_at=? WHERE side_effect_id=?
                """,
                (
                    metadata["response_id"],
                    receipt_hash,
                    result_reference,
                    now,
                    side_effect_id,
                ),
            )
            connection.execute(
                "UPDATE research_tasks SET state_version=state_version+1, "
                "updated_at=? WHERE task_id=?",
                (now, context.task_id),
            )
            next_version = int(task["state_version"]) + 1
            response = {
                "status": "failed",
                "error": reason,
                "state_version": next_version,
                "receipt_binding": binding,
                "completion_metadata": self._completion_metadata(raw),
            }
            self.kernel._event(
                connection,
                task_id=context.task_id,
                goal_id=str(attempt["goal_id"]),
                attempt_id=context.attempt_id,
                event_type="provider_call_failed",
                payload={"side_effect_id": side_effect_id, **binding},
                command_id=terminal_command_id,
                owner_epoch=context.owner_epoch,
                now=now,
            )
            self.kernel._insert_receipt(
                connection,
                task_id=context.task_id,
                command_id=terminal_command_id,
                command_type="provider_call_failed",
                payload_hash=descriptor_hash,
                outcome_reference=result_reference,
                response=response,
                owner_epoch=context.owner_epoch,
                now=now,
            )
        return next_version

    def _reject_identity(
        self,
        *,
        context: ProviderCallContext,
        operation_key: str,
        side_effect_id: str,
        descriptor: dict[str, Any],
        descriptor_hash: str,
        terminal_command_id: str,
        actual_identity: dict[str, object],
        mismatches: list[str],
    ) -> int:
        """Durably reject a known pre-dispatch identity mismatch.

        The SideEffect is already in_flight so that every authorized dispatch has
        an exact durable operation identity. No transport has started at this
        point, therefore a known failed disposition is safer than `unknown`.
        """

        now_value = self.kernel._now()
        now = _iso(now_value)
        reason = "Provider runtime identity mismatch: " + ", ".join(mismatches)
        with self.kernel._transaction() as connection:
            task, attempt = self._guard(
                connection, context=context, expected_state=True, now=now_value
            )
            effect = self.kernel._side_effect(connection, side_effect_id)
            self._assert_in_flight(effect, context, descriptor_hash)
            self._insert_action(
                connection,
                action_id=_id("inner_action", f"{context.task_id}:{operation_key}"),
                action_kind=SUPPORTED_ROLES[str(descriptor["role"])][0],
                operation_key=operation_key,
                context=context,
                attempt=attempt,
                side_effect_id=side_effect_id,
                descriptor=descriptor,
                status="rejected",
                observation={
                    "expected_provider_identity": descriptor["provider_identity"],
                    "actual_provider_identity": actual_identity,
                    "identity_mismatches": mismatches,
                    "transport_calls": 0,
                },
                now=now,
                error_code="provider_identity_mismatch",
                error_detail=reason,
            )
            connection.execute(
                "UPDATE research_side_effects SET status='failed', updated_at=? "
                "WHERE side_effect_id=?",
                (now, side_effect_id),
            )
            connection.execute(
                "UPDATE research_tasks SET state_version=state_version+1, "
                "updated_at=? WHERE task_id=?",
                (now, context.task_id),
            )
            next_version = int(task["state_version"]) + 1
            response = {
                "status": "failed",
                "error": reason,
                "actual_provider_identity": actual_identity,
                "state_version": next_version,
            }
            self.kernel._event(
                connection,
                task_id=context.task_id,
                goal_id=str(attempt["goal_id"]),
                attempt_id=context.attempt_id,
                event_type="provider_identity_rejected",
                payload={
                    "side_effect_id": side_effect_id,
                    "expected_provider_identity": descriptor["provider_identity"],
                    "actual_provider_identity": actual_identity,
                    "identity_mismatches": mismatches,
                    "transport_calls": 0,
                },
                command_id=terminal_command_id,
                owner_epoch=context.owner_epoch,
                now=now,
            )
            self.kernel._insert_receipt(
                connection,
                task_id=context.task_id,
                command_id=terminal_command_id,
                command_type="provider_identity_rejected",
                payload_hash=descriptor_hash,
                outcome_reference=side_effect_id,
                response=response,
                owner_epoch=context.owner_epoch,
                now=now,
            )
        return next_version

    def _mark_unknown(
        self,
        *,
        context: ProviderCallContext,
        operation_key: str,
        side_effect_id: str,
        descriptor: dict[str, Any],
        descriptor_hash: str,
        terminal_command_id: str,
        reason: str,
    ) -> int:
        now_value = self.kernel._now()
        now = _iso(now_value)
        with self.kernel._transaction() as connection:
            task, attempt = self._guard(
                connection, context=context, expected_state=True, now=now_value
            )
            effect = self.kernel._side_effect(connection, side_effect_id)
            self._assert_in_flight(effect, context, descriptor_hash)
            self._insert_action(
                connection,
                action_id=_id("inner_action", f"{context.task_id}:{operation_key}"),
                action_kind=SUPPORTED_ROLES[str(descriptor["role"])][0],
                operation_key=operation_key,
                context=context,
                attempt=attempt,
                side_effect_id=side_effect_id,
                descriptor=descriptor,
                status="unknown",
                observation={
                    "provider_call": {
                        "provider": descriptor["provider"],
                        "model": descriptor["model"],
                        "role": descriptor["role"],
                        "provider_identity": descriptor["provider_identity"],
                        "structured_request_hash": descriptor[
                            "structured_request_hash"
                        ],
                    },
                    "reservation_usd": descriptor["worst_case_cost_usd"],
                    "error": reason,
                },
                now=now,
                error_code="provider_dispatch_unknown",
                error_detail=reason,
            )
            connection.execute(
                "UPDATE research_side_effects SET status='unknown', "
                "updated_at=? WHERE side_effect_id=?",
                (now, side_effect_id),
            )
            connection.execute(
                "UPDATE research_tasks SET status='blocked', "
                "state_version=state_version+1, updated_at=? WHERE task_id=?",
                (now, context.task_id),
            )
            next_version = int(task["state_version"]) + 1
            response = {
                "status": "unknown",
                "error": reason,
                "side_effect_id": side_effect_id,
                "state_version": next_version,
            }
            self.kernel._event(
                connection,
                task_id=context.task_id,
                goal_id=str(attempt["goal_id"]),
                attempt_id=context.attempt_id,
                event_type="provider_call_unknown",
                payload={
                    "side_effect_id": side_effect_id,
                    "role": descriptor["role"],
                    "structured_request_hash": descriptor[
                        "structured_request_hash"
                    ],
                    "reason": reason,
                },
                command_id=terminal_command_id,
                owner_epoch=context.owner_epoch,
                now=now,
            )
            self.kernel._insert_receipt(
                connection,
                task_id=context.task_id,
                command_id=terminal_command_id,
                command_type="provider_call_unknown",
                payload_hash=descriptor_hash,
                outcome_reference=side_effect_id,
                response=response,
                owner_epoch=context.owner_epoch,
                now=now,
            )
        return next_version

    def _guard(
        self,
        connection: sqlite3.Connection,
        *,
        context: ProviderCallContext,
        expected_state: bool,
        now: datetime,
    ) -> tuple[sqlite3.Row, sqlite3.Row]:
        task = self.kernel._task(connection, context.task_id)
        attempt = self.kernel._attempt(connection, context.attempt_id)
        self.kernel._assert_nonterminal(task)
        if expected_state:
            self.kernel._assert_expected(task, context.expected_state_version)
        self.kernel._assert_owner(
            task,
            owner_id=context.owner_id,
            owner_epoch=context.owner_epoch,
            now=now,
        )
        self._assert_control(task, context.expected_control_generation)
        if (
            str(attempt["task_id"]) != context.task_id
            or str(attempt["status"]) == "terminal"
            or int(attempt["owner_epoch"]) != context.owner_epoch
        ):
            raise ResearchConflict("Provider call Attempt owner fence mismatch")
        latest = connection.execute(
            """
            SELECT checkpoint_id FROM research_checkpoints
            WHERE attempt_id=? ORDER BY sequence DESC, created_at DESC LIMIT 1
            """,
            (context.attempt_id,),
        ).fetchone()
        latest_id = str(latest["checkpoint_id"]) if latest else None
        if latest_id != context.expected_checkpoint_id:
            raise ResearchConflict("Provider call stale checkpoint fence")
        return task, attempt

    @staticmethod
    def _assert_control(task: sqlite3.Row, expected_generation: int) -> None:
        if int(task["control_generation"]) != expected_generation:
            raise ResearchConflict("Provider call stale control generation")

    @staticmethod
    def _assert_in_flight(
        effect: sqlite3.Row,
        context: ProviderCallContext,
        descriptor_hash: str,
    ) -> None:
        if (
            str(effect["task_id"]) != context.task_id
            or str(effect["attempt_id"]) != context.attempt_id
            or str(effect["request_hash"]) != descriptor_hash
            or str(effect["status"]) != "in_flight"
            or int(effect["owner_epoch"]) != context.owner_epoch
        ):
            raise ResearchConflict("Provider call SideEffect fence mismatch")

    @staticmethod
    def _insert_action(
        connection: sqlite3.Connection,
        *,
        action_id: str,
        action_kind: str,
        operation_key: str,
        context: ProviderCallContext,
        attempt: sqlite3.Row,
        side_effect_id: str,
        descriptor: dict[str, Any],
        status: str,
        observation: dict[str, Any],
        now: str,
        error_code: str | None = None,
        error_detail: str | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO research_inner_actions(
                action_id, task_id, goal_id, attempt_id,
                originating_checkpoint_id, action_kind,
                action_schema_version, action_key, request_hash,
                request_json, status, owner_epoch,
                retrieval_execution_id, retrieval_trace_id, side_effect_id,
                observation_json, error_code, error_detail,
                created_at, started_at, completed_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?,
                     ?, ?, ?, ?, ?)
            """,
            (
                action_id,
                context.task_id,
                str(attempt["goal_id"]),
                context.attempt_id,
                context.expected_checkpoint_id,
                action_kind,
                PROVIDER_ACTION_SCHEMA_VERSION,
                f"provider:{operation_key}",
                descriptor["structured_request_hash"],
                _canonical_json(descriptor),
                status,
                context.owner_epoch,
                side_effect_id,
                _canonical_json(observation),
                error_code,
                error_detail,
                now,
                now,
                now,
            ),
        )

    def _budget_snapshot(
        self, connection: sqlite3.Connection, task_id: str
    ) -> ProviderBudgetSnapshot:
        logical = transport = input_tokens = cached = output = 0
        committed = Decimal("0")
        for row in connection.execute(
            """
            SELECT observation_json FROM research_inner_actions
            WHERE task_id=? AND action_schema_version=?
              AND status IN ('succeeded', 'failed')
            """,
            (task_id, PROVIDER_ACTION_SCHEMA_VERSION),
        ).fetchall():
            observation = json.loads(str(row["observation_json"]))
            call = observation.get("provider_call", {})
            usage = call.get("usage", {})
            logical += 1
            transport += int(call.get("transport_attempts", 0))
            input_tokens += int(usage.get("input_tokens", 0))
            cached += int(usage.get("cached_input_tokens", 0))
            output += int(usage.get("output_tokens", 0))
            committed += Decimal(str(call.get("cost_usd", "0")))
        active = Decimal("0")
        for row in connection.execute(
            """
            SELECT request_json FROM research_side_effects
            WHERE task_id=? AND effect_kind=?
              AND status IN ('reserved', 'in_flight', 'unknown')
            """,
            (task_id, PROVIDER_EFFECT_KIND),
        ).fetchall():
            request = json.loads(str(row["request_json"]))
            active += Decimal(str(request["worst_case_cost_usd"]))
        return ProviderBudgetSnapshot(
            logical_calls=logical,
            transport_calls=transport,
            input_tokens=input_tokens,
            cached_input_tokens=cached,
            output_tokens=output,
            committed_cost_usd=_decimal_text(committed),
            active_reserved_cost_usd=_decimal_text(active),
            accounted_cost_usd=_decimal_text(committed + active),
        )

    def _assert_run_budget_binding(
        self,
        connection: sqlite3.Connection,
        policy: ProviderRunBudgetPolicy,
    ) -> None:
        placeholders = ",".join("?" for _ in policy.task_ids)
        rows = connection.execute(
            f"""
            SELECT task_id, evidence_policy_json FROM research_goals
            WHERE revision=1 AND task_id IN ({placeholders})
            ORDER BY task_id
            """,
            tuple(policy.task_ids),
        ).fetchall()
        if len(rows) != len(policy.task_ids):
            raise ResearchValidationError(
                "Provider run budget membership is incomplete in the durable database"
            )
        expected = policy.manifest()
        expected_hash = policy.policy_hash
        for row in rows:
            evidence_policy = json.loads(str(row["evidence_policy_json"]))
            binding = evidence_policy.get("provider_run_budget")
            if not isinstance(binding, dict):
                raise ResearchValidationError(
                    "Provider Task has no durable run budget binding"
                )
            observed = {
                key: binding.get(key)
                for key in expected
            }
            if observed != expected or binding.get("policy_hash") != expected_hash:
                raise ResearchValidationError(
                    "Provider Task run budget binding does not match the frozen policy"
                )

    def _run_budget_snapshot(
        self,
        connection: sqlite3.Connection,
        task_ids: tuple[str, ...],
    ) -> ProviderRunBudgetSnapshot:
        placeholders = ",".join("?" for _ in task_ids)
        committed_logical = committed_http = 0
        committed_input = committed_output = 0
        committed_cost = Decimal("0")
        action_rows = connection.execute(
            f"""
            SELECT observation_json FROM research_inner_actions
            WHERE task_id IN ({placeholders}) AND action_schema_version=?
              AND status IN ('succeeded', 'failed')
            """,
            (*task_ids, PROVIDER_ACTION_SCHEMA_VERSION),
        ).fetchall()
        for row in action_rows:
            observation = json.loads(str(row["observation_json"]))
            call = observation.get("provider_call", {})
            usage = call.get("usage", {})
            committed_logical += 1
            committed_http += int(call.get("transport_attempts", 0))
            committed_input += int(usage.get("input_tokens", 0))
            committed_output += int(usage.get("output_tokens", 0))
            committed_cost += Decimal(str(call.get("cost_usd", "0")))

        active_logical = active_http = 0
        active_input = active_output = 0
        active_cost = Decimal("0")
        effect_rows = connection.execute(
            f"""
            SELECT request_json FROM research_side_effects
            WHERE task_id IN ({placeholders}) AND effect_kind=?
              AND status IN ('reserved', 'in_flight', 'unknown')
            """,
            (*task_ids, PROVIDER_EFFECT_KIND),
        ).fetchall()
        for row in effect_rows:
            request = json.loads(str(row["request_json"]))
            price = request.get("price_table", {})
            active_logical += 1
            active_http += int(
                price.get(
                    "reservation_transport_attempts",
                    self.price_policy.reservation_transport_attempts,
                )
            )
            active_input += int(request.get("input_token_upper_bound", 0))
            active_output += int(request.get("max_output_tokens", 0))
            active_cost += Decimal(str(request.get("worst_case_cost_usd", "0")))
        return ProviderRunBudgetSnapshot(
            task_ids=tuple(sorted(task_ids)),
            committed_logical_calls=committed_logical,
            active_logical_reservations=active_logical,
            accounted_logical_calls=committed_logical + active_logical,
            committed_http_attempts=committed_http,
            active_http_attempt_reservations=active_http,
            accounted_http_attempts=committed_http + active_http,
            committed_input_tokens=committed_input,
            active_input_token_reservations=active_input,
            accounted_input_tokens=committed_input + active_input,
            committed_output_tokens=committed_output,
            active_output_token_reservations=active_output,
            accounted_output_tokens=committed_output + active_output,
            committed_cost_usd=_decimal_text(committed_cost),
            active_reserved_cost_usd=_decimal_text(active_cost),
            accounted_cost_usd=_decimal_text(committed_cost + active_cost),
        )

    @staticmethod
    def _normalize_usage(value: object) -> dict[str, int]:
        if not isinstance(value, dict):
            raise ResearchValidationError("Provider usage is required for cost receipt")
        input_tokens = value.get("input_tokens", value.get("prompt_tokens"))
        output_tokens = value.get("output_tokens", value.get("completion_tokens"))
        details = value.get("prompt_tokens_details")
        cached = value.get(
            "cached_input_tokens",
            value.get("prompt_cache_hit_tokens", value.get("cached_tokens", 0)),
        )
        if isinstance(details, dict):
            cached = details.get("cached_tokens", cached)
        if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
            raise ResearchValidationError("Provider usage token counts are incomplete")
        if (
            input_tokens < 0
            or output_tokens < 0
            or not isinstance(cached, int)
            or cached < 0
            or cached > input_tokens
        ):
            raise ResearchValidationError("Provider usage token counts are invalid")
        return {
            "input_tokens": input_tokens,
            "cached_input_tokens": cached,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }

    @staticmethod
    def _actual_provider_identity(provider: object, role: str) -> dict[str, object]:
        base_url = getattr(provider, "base_url", None)
        effort = getattr(provider, "reasoning_effort", None)
        return {
            "provider_protocol": getattr(provider, "name", None),
            "base_url": (
                str(base_url).rstrip("/") if isinstance(base_url, str) else None
            ),
            "model": getattr(provider, "model", None),
            "role": role,
            "thinking_enabled": getattr(provider, "thinking_enabled", None),
            "reasoning_effort": None if effort in (None, "") else str(effort),
        }

    @staticmethod
    def _has_operation_id(value: object) -> bool:
        return isinstance(value, str) and bool(value.strip())

    @staticmethod
    def _identity_mismatches(
        *, expected: object, actual: dict[str, object]
    ) -> list[str]:
        if not isinstance(expected, dict):
            raise ResearchValidationError("authorized Provider identity is invalid")
        return [
            key
            for key in (
                "provider_protocol",
                "base_url",
                "model",
                "role",
                "thinking_enabled",
                "reasoning_effort",
            )
            if (
                type(actual.get(key)) is not type(expected.get(key))
                or actual.get(key) != expected.get(key)
            )
        ]

    @staticmethod
    def _response_metadata(raw: object, usage: dict[str, int]) -> dict[str, Any]:
        del usage
        retry_count = int(getattr(raw, "retry_count", 0))
        if retry_count < 0 or retry_count > 1:
            raise ResearchValidationError("Provider retry_count exceeds Gate B cap")
        response_id = getattr(raw, "response_id", None)
        if not isinstance(response_id, str) or not response_id.strip():
            raise ResearchValidationError(
                "Provider response/operation ID is required for a complete receipt"
            )
        response_id = response_id.strip()
        latency = getattr(raw, "latency_ms", 0.0)
        return {
            "response_id": str(response_id),
            "finish_reason": (
                str(getattr(raw, "finish_reason"))
                if getattr(raw, "finish_reason", None) is not None
                else None
            ),
            "latency_ms": float(latency) if isinstance(latency, (int, float)) else 0.0,
            "retry_count": retry_count,
            "transport_attempts": retry_count + 1,
        }

    @staticmethod
    def _completion_metadata(raw: object) -> dict[str, Any]:
        return {
            "finish_reason": getattr(raw, "finish_reason", None),
            "usage": getattr(raw, "usage", None),
            "response_id": getattr(raw, "response_id", None),
            "latency_ms": getattr(raw, "latency_ms", None),
            "retry_count": int(getattr(raw, "retry_count", 0)),
            "content_received": True,
        }

    @staticmethod
    def _known_failure_response(exc: Exception) -> _KnownFailureResponse | None:
        metadata = getattr(exc, "completion_metadata", None)
        if not isinstance(metadata, dict):
            return None
        if not isinstance(metadata.get("usage"), dict):
            return None
        if not metadata.get("content_received") and not metadata.get("response_id"):
            return None
        return _KnownFailureResponse(
            usage=dict(metadata["usage"]),
            response_id=(
                str(metadata["response_id"])
                if metadata.get("response_id") is not None
                else None
            ),
            finish_reason=(
                str(metadata["finish_reason"])
                if metadata.get("finish_reason") is not None
                else None
            ),
            latency_ms=float(metadata.get("latency_ms") or 0.0),
            retry_count=int(metadata.get("retry_count") or 0),
        )

    @staticmethod
    def _response_from_payload(
        payload: dict[str, Any],
        *,
        response_schema: type[SchemaT],
        deduplicated: bool,
    ) -> DurableStructuredResponse[SchemaT]:
        return DurableStructuredResponse(
            output=response_schema.model_validate(payload["output"]),
            finish_reason=payload.get("finish_reason"),
            usage=dict(payload["usage"]),
            response_id=str(payload["response_id"]),
            latency_ms=float(payload.get("latency_ms", 0.0)),
            retry_count=int(payload.get("retry_count", 0)),
            receipt_binding=dict(payload["receipt_binding"]),
            state_version=int(payload["state_version"]),
            deduplicated=deduplicated,
        )
