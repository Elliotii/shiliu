"""Small explicit DTO conversions, with no JSON guessing or domain remapping."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Mapping, Sequence
import json


def json_value(value: Any) -> Any:
    """Read an explicitly identified JSON field, retaining its historical root."""
    return json.loads(value) if isinstance(value, str) else value


def timestamp_value(value: str | datetime | None) -> datetime | None:
    """Bind a named nullable timestamp without stringifying native PG values."""
    if value is None:
        return None
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("An explicit timestamp timezone is required")
    return parsed.astimezone(timezone.utc)


def json_object(value: Any) -> dict[str, Any]:
    """Decode an explicitly identified JSON object in historical or PG DTOs."""
    if value is None:
        return {}
    if isinstance(value, str):
        value = json.loads(value or "{}")
    if not isinstance(value, Mapping):
        raise ValueError("JSON object required")
    return dict(value)


def json_array(value: Any) -> list[Any]:
    """Decode an explicitly identified JSON array; do not infer column types."""
    if value is None:
        return []
    if isinstance(value,str):
        value=json.loads(value or "[]")
    if not isinstance(value,list):
        raise ValueError("JSON array required")
    return list(value)


def iso_time(value: datetime, *, timespec: str = "seconds") -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("An explicit timestamp timezone is required")
    return value.astimezone(timezone.utc).isoformat(timespec=timespec)


def row_dto(row: Mapping[str, Any], *, timestamps: Sequence[str] = (),
            dates: Sequence[str] = (), timespec: str = "seconds") -> dict[str, Any]:
    """Convert only named top-level SQL time/date fields; preserve missing keys.

    JSONB is already a native object. SQL NULL and top-level JSON null both load
    as None in psycopg; query `column IS NULL` when that distinction is needed.
    Nested JSON null versus absent fields stays distinguishable without decoding.
    """
    result = dict(row)
    for key in timestamps:
        if key in result and result[key] is not None:
            if not isinstance(result[key], datetime):
                raise TypeError("Timestamp DTO field must be datetime")
            result[key] = iso_time(result[key], timespec=timespec)
    for key in dates:
        if key in result and result[key] is not None:
            if type(result[key]) is not date:
                raise TypeError("Date DTO field must be date")
            result[key] = result[key].isoformat()
    return result


def assistant_run_dto(row: Mapping[str, Any], *, current: bool) -> dict[str, Any]:
    """PG row projection of AssistantRunStore._run/_with_actions, without I/O.

    JSONB values are already decoded. Keep the legacy API names and ISO-second
    timestamp convention (db.utc_now); recovery counters live in working_state.
    The caller determines current from the thread's insertion order under lock.
    """
    run = row_dto(row, timestamps=('created_at', 'updated_at', 'started_at', 'completed_at'))
    run['working_state'] = run.pop('working_state_json')
    run['usage'] = run.pop('usage_json')
    run['cancel_requested'] = bool(run['cancel_requested'])
    status = str(run['status'])
    code = str(run.get('last_error_code') or '')
    recovery_attempts = int(run['working_state'].get('context_recovery_attempts', 0))
    compaction_retries = int(run['working_state'].get('compaction_retries', 0))
    resumable = current and (
        status in {'interrupted', 'budget_exhausted'}
        and (code != 'context_budget_exceeded' or recovery_attempts == 0)
        or status == 'failed' and code == 'context_compaction_failed' and compaction_retries == 0
    )
    run['actions'] = {
        'resume': resumable,
        'abandon': current and status in {'queued', 'running', 'interrupted', 'budget_exhausted', 'failed'},
        'terminated': status == 'cancelled',
        'current': current,
        'reason': 'run_superseded' if not current and status in {'interrupted', 'budget_exhausted'} else (code or None),
    }
    return run
