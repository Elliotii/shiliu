from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Generic, TypeVar

from pydantic import BaseModel

from shiliu.domain import PipelineError
from shiliu.llm import OpenAICompatibleProvider, parse_json_content


SchemaT = TypeVar("SchemaT", bound=BaseModel)
JSON_REPAIR_PROMPT_VERSION = "json-repair-v2-audited-semantic-selection"


class AuditedJsonCaller(Generic[SchemaT]):
    """Persist raw model responses before validation and repair without corpus replay."""

    def __init__(
        self,
        *,
        provider: OpenAICompatibleProvider,
        repair_provider: OpenAICompatibleProvider,
    ) -> None:
        self.provider = provider
        self.repair_provider = repair_provider

    def call(
        self,
        *,
        call_dir: Path,
        prompt: str,
        prompt_version: str,
        schema: type[SchemaT],
        schema_hint: str,
        max_tokens: int,
        input_ids: list[str],
        validator: Callable[[SchemaT], None] | None = None,
        resume: bool = False,
    ) -> tuple[SchemaT, dict[str, Any]]:
        if call_dir.exists():
            if not resume:
                raise FileExistsError(call_dir)
            return self._resume(
                call_dir=call_dir,
                prompt=prompt,
                prompt_version=prompt_version,
                schema=schema,
                schema_hint=schema_hint,
                max_tokens=max_tokens,
                input_ids=input_ids,
                validator=validator,
            )
        call_dir.mkdir(parents=True, exist_ok=False)
        prompt_path = call_dir / "prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        audit: dict[str, Any] = {
            "status": "requesting",
            "prompt_version": prompt_version,
            "model": self.provider.model,
            "parameters": {
                "thinking_enabled": self.provider.thinking_enabled,
                "reasoning_effort": self.provider.reasoning_effort,
                "max_tokens": max_tokens,
            },
            "input_ids": input_ids,
            "input_count": len(input_ids),
            "input_chars": len(prompt),
            "prompt_path": prompt_path.name,
            "started_at": _utc_now(),
            "raw_response_path": None,
            "usage": None,
            "repair": None,
            "request_attempt_count": 1,
        }
        audit_path = call_dir / "audit.json"
        _write_json(audit_path, audit)
        started = time.monotonic()
        try:
            response = self.provider.complete_raw(prompt, max_tokens=max_tokens)
        except PipelineError as exc:
            audit.update(
                status="request_failed",
                error_code=exc.code,
                error_message=str(exc),
                elapsed_seconds=round(time.monotonic() - started, 3),
                finished_at=_utc_now(),
            )
            _write_json(audit_path, audit)
            raise

        raw_path = call_dir / "raw-response.txt"
        raw_path.write_text(response.content, encoding="utf-8")
        reasoning_path: Path | None = None
        if response.reasoning_content:
            reasoning_path = call_dir / "reasoning-response.txt"
            reasoning_path.write_text(response.reasoning_content, encoding="utf-8")
        audit.update(
            status="raw_received",
            raw_response_path=raw_path.name,
            raw_response_chars=len(response.content),
            finish_reason=response.finish_reason,
            response_id=response.response_id,
            reasoning_response_path=reasoning_path.name if reasoning_path else None,
            usage=response.usage,
            elapsed_seconds=round(time.monotonic() - started, 3),
            raw_received_at=_utc_now(),
        )
        _write_json(audit_path, audit)

        if not response.content.strip():
            audit.update(
                status="empty_response",
                error_code="empty_model_output",
                error_message="模型返回为空",
                finished_at=_utc_now(),
            )
            _write_json(audit_path, audit)
            raise PipelineError("模型返回为空", code="empty_model_output", retryable=True)

        try:
            result = parse_json_content(response.content, schema)
            if validator:
                validator(result)
        except PipelineError as exc:
            validation_path = call_dir / "validation-error.txt"
            validation_path.write_text(str(exc), encoding="utf-8")
            result, repair_audit = self._repair(
                call_dir=call_dir,
                raw=response.content,
                validation_error=str(exc),
                schema=schema,
                schema_hint=schema_hint,
                max_tokens=max_tokens,
                validator=validator,
            )
            audit["repair"] = repair_audit
            _write_repair_semantic_diff(
                call_dir=call_dir,
                original_raw=response.content,
                repaired_value=result.model_dump(mode="json"),
                validation_error=str(exc),
                stage_id=prompt_version,
                attempt_id=str(repair_audit.get("attempt_count") or 1),
            )

        output = result.model_dump(mode="json")
        _write_json(call_dir / "parsed-output.json", output)
        audit.update(status="completed", finished_at=_utc_now())
        _write_json(audit_path, audit)
        return result, audit

    def _resume(
        self,
        *,
        call_dir: Path,
        prompt: str,
        prompt_version: str,
        schema: type[SchemaT],
        schema_hint: str,
        max_tokens: int,
        input_ids: list[str],
        validator: Callable[[SchemaT], None] | None,
    ) -> tuple[SchemaT, dict[str, Any]]:
        audit_path = call_dir / "audit.json"
        if not audit_path.is_file():
            raise PipelineError(
                "调用目录缺少 audit.json，不能安全恢复",
                code="taxonomy_resume_corrupt",
                retryable=False,
            )
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        prompt_path = call_dir / str(audit.get("prompt_path") or "prompt.txt")
        if (
            audit.get("prompt_version") != prompt_version
            or not prompt_path.is_file()
            or prompt_path.read_text(encoding="utf-8") != prompt
            or audit.get("input_ids") != input_ids
        ):
            raise PipelineError(
                "恢复输入与原调用不一致",
                code="taxonomy_resume_input_mismatch",
                retryable=False,
            )
        if audit.get("status") == "completed":
            parsed_path = call_dir / "parsed-output.json"
            if not parsed_path.is_file():
                raise PipelineError(
                    "已完成调用缺少 parsed-output.json",
                    code="taxonomy_resume_corrupt",
                    retryable=False,
                )
            result = schema.model_validate_json(parsed_path.read_text(encoding="utf-8"))
            if validator:
                validator(result)
            return result, audit

        raw_name = audit.get("raw_response_path")
        if not raw_name:
            request_attempt = int(audit.get("request_attempt_count") or 1)
            expected_raw = (
                call_dir / "raw-response.txt"
                if request_attempt == 1
                else call_dir / f"raw-response-{request_attempt:02d}.txt"
            )
            if expected_raw.is_file():
                raw_name = expected_raw.name
        validation_path = call_dir / "validation-error.txt"
        if raw_name and (call_dir / str(raw_name)).is_file():
            raw = (call_dir / str(raw_name)).read_text(encoding="utf-8")
            if raw.strip() and not validation_path.is_file():
                try:
                    result = parse_json_content(raw, schema)
                    if validator:
                        validator(result)
                except PipelineError as exc:
                    validation_path.write_text(str(exc), encoding="utf-8")
                else:
                    _write_json(call_dir / "parsed-output.json", result.model_dump(mode="json"))
                    audit.update(status="completed", finished_at=_utc_now())
                    _write_json(audit_path, audit)
                    return result, audit
            if raw.strip() and validation_path.is_file():
                result, repair_audit = self._repair(
                    call_dir=call_dir,
                    raw=raw,
                    validation_error=validation_path.read_text(encoding="utf-8"),
                    schema=schema,
                    schema_hint=schema_hint,
                    max_tokens=max_tokens,
                    validator=validator,
                    resume=True,
                )
                output = result.model_dump(mode="json")
                _write_repair_semantic_diff(
                    call_dir=call_dir,
                    original_raw=raw,
                    repaired_value=output,
                    validation_error=validation_path.read_text(encoding="utf-8"),
                    stage_id=prompt_version,
                    attempt_id=str(repair_audit.get("attempt_count") or 1),
                )
                _write_json(call_dir / "parsed-output.json", output)
                audit.update(status="completed", repair=repair_audit, finished_at=_utc_now())
                _write_json(audit_path, audit)
                return result, audit

        _preserve_attempt(audit, count_key="request_attempt_count")
        attempt = int(audit.get("request_attempt_count") or 1) + 1
        audit.update(
            status="requesting",
            request_attempt_count=attempt,
            started_at=_utc_now(),
            error_code=None,
            error_message=None,
        )
        _write_json(audit_path, audit)
        started = time.monotonic()
        try:
            response = self.provider.complete_raw(prompt, max_tokens=max_tokens)
        except PipelineError as exc:
            audit.update(
                status="request_failed",
                error_code=exc.code,
                error_message=str(exc),
                elapsed_seconds=round(time.monotonic() - started, 3),
                finished_at=_utc_now(),
            )
            _write_json(audit_path, audit)
            raise
        raw_path = call_dir / f"raw-response-{attempt:02d}.txt"
        raw_path.write_text(response.content, encoding="utf-8")
        audit.update(
            status="raw_received",
            raw_response_path=raw_path.name,
            raw_response_chars=len(response.content),
            finish_reason=response.finish_reason,
            response_id=response.response_id,
            usage=response.usage,
            elapsed_seconds=round(time.monotonic() - started, 3),
            raw_received_at=_utc_now(),
        )
        _write_json(audit_path, audit)
        if not response.content.strip():
            audit.update(
                status="empty_response",
                error_code="empty_model_output",
                error_message="模型返回为空",
                finished_at=_utc_now(),
            )
            _write_json(audit_path, audit)
            raise PipelineError("模型返回为空", code="empty_model_output", retryable=True)
        try:
            result = parse_json_content(response.content, schema)
            if validator:
                validator(result)
        except PipelineError as exc:
            validation_path.write_text(str(exc), encoding="utf-8")
            result, repair_audit = self._repair(
                call_dir=call_dir,
                raw=response.content,
                validation_error=str(exc),
                schema=schema,
                schema_hint=schema_hint,
                max_tokens=max_tokens,
                validator=validator,
                resume=True,
            )
            audit["repair"] = repair_audit
            _write_repair_semantic_diff(
                call_dir=call_dir,
                original_raw=response.content,
                repaired_value=result.model_dump(mode="json"),
                validation_error=str(exc),
                stage_id=prompt_version,
                attempt_id=str(repair_audit.get("attempt_count") or 1),
            )
        _write_json(call_dir / "parsed-output.json", result.model_dump(mode="json"))
        audit.update(status="completed", finished_at=_utc_now())
        _write_json(audit_path, audit)
        return result, audit

    def _repair(
        self,
        *,
        call_dir: Path,
        raw: str,
        validation_error: str,
        schema: type[SchemaT],
        schema_hint: str,
        max_tokens: int,
        validator: Callable[[SchemaT], None] | None,
        resume: bool = False,
    ) -> tuple[SchemaT, dict[str, Any]]:
        prompt = (
            "你是 JSON Repair 工具。只修正下面原始响应的 JSON 语法和结构，不补充原始语料中"
            "不存在的事实。必须逐项遵守校验错误中的数值上限。若列表超过预算，不得按输出顺序"
            "静默截断；应按内容中心性、置信度和证据强度保留允许数量，其余视为可审计的"
            "semantic_selection。不得重新执行原任务。只输出修复后的 JSON。\n\n"
            f"精简 Schema：\n{schema_hint}\n\n"
            f"校验错误（已截断为修复所需摘要）：\n{validation_error[:3500]}\n\n"
            f"原始响应：\n{raw}"
        )
        existing_audit_path = call_dir / "repair-audit.json"
        repair_attempt = 1
        attempt_history: list[dict[str, Any]] = []
        if resume and existing_audit_path.is_file():
            existing = json.loads(existing_audit_path.read_text(encoding="utf-8"))
            existing_raw = call_dir / str(existing.get("raw_response_path") or "")
            if existing_raw.is_file() and existing_raw.read_text(encoding="utf-8").strip():
                try:
                    result = parse_json_content(existing_raw.read_text(encoding="utf-8"), schema)
                    if validator:
                        validator(result)
                except PipelineError:
                    pass
                else:
                    if existing.get("status") != "completed":
                        existing.update(status="completed", finished_at=_utc_now())
                        _write_json(existing_audit_path, existing)
                    return result, existing
            _preserve_attempt(existing, count_key="attempt_count")
            attempt_history = list(existing.get("attempt_history") or [])
            repair_attempt = int(existing.get("attempt_count") or 1) + 1
        repair_prompt_path = call_dir / "repair-prompt.txt"
        repair_prompt_path.write_text(prompt, encoding="utf-8")
        repair_audit: dict[str, Any] = {
            "status": "requesting",
            "prompt_version": JSON_REPAIR_PROMPT_VERSION,
            "model": self.repair_provider.model,
            "input_chars": len(prompt),
            "prompt_path": repair_prompt_path.name,
            "original_prompt_replayed": False,
            "started_at": _utc_now(),
            "usage": None,
            "attempt_count": repair_attempt,
            "attempt_history": attempt_history,
        }
        repair_audit_path = call_dir / "repair-audit.json"
        _write_json(repair_audit_path, repair_audit)
        started = time.monotonic()
        try:
            response = self.repair_provider.complete_raw(prompt, max_tokens=max_tokens)
        except PipelineError as exc:
            repair_audit.update(
                status="request_failed",
                error_code=exc.code,
                error_message=str(exc),
                elapsed_seconds=round(time.monotonic() - started, 3),
                finished_at=_utc_now(),
            )
            _write_json(repair_audit_path, repair_audit)
            raise
        repair_raw_path = call_dir / (
            "repair-raw-response.txt"
            if repair_attempt == 1
            else f"repair-raw-response-{repair_attempt:02d}.txt"
        )
        repair_raw_path.write_text(response.content, encoding="utf-8")
        repair_audit.update(
            status="raw_received",
            raw_response_path=repair_raw_path.name,
            raw_response_chars=len(response.content),
            usage=response.usage,
            finish_reason=response.finish_reason,
            response_id=response.response_id,
            elapsed_seconds=round(time.monotonic() - started, 3),
            raw_received_at=_utc_now(),
        )
        _write_json(repair_audit_path, repair_audit)
        try:
            result = parse_json_content(response.content, schema)
            if validator:
                validator(result)
        except PipelineError as exc:
            repair_audit.update(
                status="validation_failed",
                error_code=exc.code,
                error_message=str(exc),
                finished_at=_utc_now(),
            )
            _write_json(repair_audit_path, repair_audit)
            raise
        repair_audit.update(status="completed", finished_at=_utc_now())
        _write_json(repair_audit_path, repair_audit)
        return result, repair_audit


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _write_repair_semantic_diff(
    *,
    call_dir: Path,
    original_raw: str,
    repaired_value: Any,
    validation_error: str,
    stage_id: str,
    attempt_id: str,
) -> None:
    """Persist an explicit field-level account of every Repair transformation."""

    try:
        original = _extract_json_value(original_raw)
    except (ValueError, json.JSONDecodeError):
        events = [
            {
                "stage_id": stage_id,
                "attempt_id": attempt_id,
                "content_id": None,
                "candidate_id": None,
                "field_path": "$",
                "original_value": original_raw,
                "repaired_value": repaired_value,
                "change_type": "syntax_only",
                "reason": "原始响应不是可解析 JSON；Repair 形成可校验 JSON。",
                "validation_error": validation_error,
                "evidence": "json_parse_failed",
                "timestamp": _utc_now(),
            }
        ]
    else:
        events = _semantic_diff_events(
            original,
            repaired_value,
            stage_id=stage_id,
            attempt_id=attempt_id,
            validation_error=validation_error,
        )
        if not events:
            events = [
                {
                    "stage_id": stage_id,
                    "attempt_id": attempt_id,
                    "content_id": None,
                    "candidate_id": None,
                    "field_path": "$",
                    "original_value": original,
                    "repaired_value": repaired_value,
                    "change_type": "schema_only",
                    "reason": "值未改变；Repair 仅使响应满足严格 Schema。",
                    "validation_error": validation_error,
                    "evidence": "no_value_difference",
                    "timestamp": _utc_now(),
                }
            ]
    _write_json(
        call_dir / "repair-semantic-diff.json",
        {
            "version": "repair-semantic-diff-v1",
            "events": events,
            "semantic_change_count": sum(
                item["change_type"]
                in {"semantic_selection", "semantic_addition", "semantic_removal"}
                for item in events
            ),
            "syntax_only_count": sum(
                item["change_type"] == "syntax_only" for item in events
            ),
        },
    )


def _extract_json_value(raw: str) -> Any:
    text = raw.strip()
    if text.startswith("```") and text.endswith("```"):
        first_newline = text.find("\n")
        text = text[first_newline + 1 : -3].strip()
    start_candidates = [value for value in (text.find("{"), text.find("[")) if value >= 0]
    if not start_candidates:
        raise ValueError("no JSON value")
    start = min(start_candidates)
    end = max(text.rfind("}"), text.rfind("]"))
    if end < start:
        raise ValueError("incomplete JSON value")
    return json.loads(text[start : end + 1])


def _semantic_diff_events(
    original: Any,
    repaired: Any,
    *,
    stage_id: str,
    attempt_id: str,
    validation_error: str,
    path: str = "$",
    context: dict[str, str | None] | None = None,
) -> list[dict[str, Any]]:
    context = dict(context or {"content_id": None, "candidate_id": None})
    if isinstance(original, dict):
        for key in ("content_id", "candidate_id"):
            if isinstance(original.get(key), str):
                context[key] = original[key]
    if isinstance(repaired, dict):
        for key in ("content_id", "candidate_id"):
            if isinstance(repaired.get(key), str):
                context[key] = repaired[key]
    if type(original) is type(repaired):
        if isinstance(original, dict):
            events: list[dict[str, Any]] = []
            for key in sorted(set(original) | set(repaired)):
                child = f"{path}.{key}"
                if key not in original:
                    events.append(_diff_event(
                        stage_id, attempt_id, context, child, None, repaired[key],
                        "semantic_addition", validation_error,
                    ))
                elif key not in repaired:
                    events.append(_diff_event(
                        stage_id, attempt_id, context, child, original[key], None,
                        "semantic_removal", validation_error,
                    ))
                else:
                    events.extend(_semantic_diff_events(
                        original[key], repaired[key], stage_id=stage_id,
                        attempt_id=attempt_id, validation_error=validation_error,
                        path=child, context=context,
                    ))
            return events
        if isinstance(original, list):
            if original == repaired:
                return []
            change_type = "normalization"
            if len(repaired) < len(original):
                change_type = (
                    "semantic_selection"
                    if "max_length" in validation_error or "最多" in validation_error
                    else "semantic_removal"
                )
            elif len(repaired) > len(original):
                change_type = "semantic_addition"
            return [_diff_event(
                stage_id, attempt_id, context, path, original, repaired,
                change_type, validation_error,
            )]
        if original == repaired:
            return []
        return [_diff_event(
            stage_id, attempt_id, context, path, original, repaired,
            "normalization", validation_error,
        )]
    return [_diff_event(
        stage_id, attempt_id, context, path, original, repaired,
        "schema_only", validation_error,
    )]


def _diff_event(
    stage_id: str,
    attempt_id: str,
    context: dict[str, str | None],
    field_path: str,
    original_value: Any,
    repaired_value: Any,
    change_type: str,
    validation_error: str,
) -> dict[str, Any]:
    return {
        "stage_id": stage_id,
        "attempt_id": attempt_id,
        "content_id": context.get("content_id"),
        "candidate_id": context.get("candidate_id"),
        "field_path": field_path,
        "original_value": original_value,
        "repaired_value": repaired_value,
        "change_type": change_type,
        "reason": "Repair 后字段值发生可审计变化。",
        "validation_error": validation_error,
        "evidence": "raw_response_vs_validated_repair",
        "timestamp": _utc_now(),
    }


def _preserve_attempt(audit: dict[str, Any], *, count_key: str) -> None:
    """Keep usage/latency for an attempt before top-level audit fields are reused."""

    attempt = int(audit.get(count_key) or 1)
    history = audit.setdefault("attempt_history", [])
    if any(int(item.get("attempt") or 0) == attempt for item in history):
        return
    history.append(
        {
            "attempt": attempt,
            "status": audit.get("status"),
            "usage": audit.get("usage"),
            "elapsed_seconds": audit.get("elapsed_seconds"),
            "response_id": audit.get("response_id"),
            "finish_reason": audit.get("finish_reason"),
            "raw_response_path": audit.get("raw_response_path"),
            "error_code": audit.get("error_code"),
            "error_message": audit.get("error_message"),
        }
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
