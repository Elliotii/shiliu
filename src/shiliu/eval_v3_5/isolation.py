from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


ALLOWED_GOLD_PATHS = frozenset(
    {
        "research/v3_5/gold/development_gold.8_cases.locked.jsonl",
        "research/v3_5/gold/V3_5_EVAL_PROTOCOL.locked.md",
        "research/v3_5/gold/HELDOUT_ISOLATION_CONTRACT.md",
    }
)
FORBIDDEN_PATH_PATTERNS = (
    "eval_gold.locked",
    "eval_gold_review",
    "heldout_gold",
    "master_gold",
    "master.18_cases",
    "adjudicated",
    "gold_lock_manifest",
    "gold_lock_audit",
    "master_case_membership",
    "development_heldout_split",
    "reason_code_registry",
    "human_reviews",
    "review_packets",
    "eval_queries.locked",
)


class HeldoutAccessError(RuntimeError):
    code = "forbidden_stage3a_input"


@dataclass
class HeldoutAccessGuard:
    repository_root: Path
    runtime_input_paths: list[str] = field(default_factory=list)
    forbidden_open_attempts: list[str] = field(default_factory=list)

    def validate_path(self, path: str | Path) -> Path:
        resolved = Path(path).resolve()
        normalized = resolved.as_posix().lower()
        matches = [value for value in FORBIDDEN_PATH_PATTERNS if value in normalized]
        if matches:
            self.forbidden_open_attempts.append(str(resolved))
            raise HeldoutAccessError(
                f"Stage 3A input is forbidden by held-out isolation: {matches[0]}"
            )
        self.runtime_input_paths.append(self._display_path(resolved))
        return resolved

    def read_text(self, path: str | Path, *, encoding: str = "utf-8") -> str:
        return self.validate_path(path).read_text(encoding=encoding)

    def read_bytes(self, path: str | Path) -> bytes:
        return self.validate_path(path).read_bytes()

    def assert_gold_whitelist(self, paths: Iterable[str | Path]) -> None:
        for path in paths:
            resolved = Path(path).resolve()
            try:
                relative = resolved.relative_to(self.repository_root.resolve()).as_posix()
            except ValueError:
                continue
            if relative.startswith("research/v3_5/gold/") and relative not in ALLOWED_GOLD_PATHS:
                self.forbidden_open_attempts.append(str(resolved))
                raise HeldoutAccessError(f"Stage 3A Gold input is not whitelisted: {relative}")

    def audit_record(
        self,
        *,
        source_files_scanned: Iterable[str],
        test_files_scanned: Iterable[str],
        violations: Iterable[str] = (),
    ) -> dict[str, object]:
        return {
            "allowed_gold_paths": sorted(ALLOWED_GOLD_PATHS),
            "forbidden_path_patterns": list(FORBIDDEN_PATH_PATTERNS),
            "source_files_scanned": sorted(set(source_files_scanned)),
            "test_files_scanned": sorted(set(test_files_scanned)),
            "runtime_input_paths": sorted(set(self.runtime_input_paths)),
            "forbidden_open_attempts": list(self.forbidden_open_attempts),
            "heldout_formal_run_executed": False,
            "heldout_labels_loaded": False,
            "heldout_evidence_loaded": False,
            "heldout_case_specific_rules_detected": False,
            "violations": list(violations),
        }

    def _display_path(self, path: Path) -> str:
        try:
            return path.relative_to(self.repository_root.resolve()).as_posix()
        except ValueError:
            return str(path)
