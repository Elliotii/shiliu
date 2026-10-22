"""Small, dependency-free parser for HTTP Retry-After values."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math


def parse_retry_after(value: object, *, now: datetime | None = None) -> float | None:
    """Return a non-negative delay in seconds for delta or HTTP-date values."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        seconds = float(text)
    except ValueError:
        try:
            target = parsedate_to_datetime(text)
        except (TypeError, ValueError, OverflowError):
            return None
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        seconds = (target.astimezone(timezone.utc) - current.astimezone(timezone.utc)).total_seconds()
    if not math.isfinite(seconds):
        return None
    return max(0.0, seconds)
