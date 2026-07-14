from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path


REDACTIONS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)((?:api[_-]?key|sessdata|bili_jct)\s*[:=]\s*)[^\s,;]+"),
)


def redact_text(value: str) -> str:
    result = value
    for pattern in REDACTIONS:
        result = pattern.sub(r"\1[REDACTED]", result)
    return result


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(record.getMessage())
        record.args = ()
        return True


def configure_logging(logs_dir: Path) -> Path:
    logs_dir.mkdir(parents=True, exist_ok=True)
    path = (logs_dir / "shiliu.log").resolve()
    root = logging.getLogger("shiliu")
    root.setLevel(logging.INFO)
    for handler in root.handlers:
        if getattr(handler, "baseFilename", None) == str(path):
            return path
    handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(RedactingFilter())
    root.addHandler(handler)
    root.propagate = False
    return path
