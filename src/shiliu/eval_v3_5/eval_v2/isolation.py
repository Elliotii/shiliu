from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PROTECTED_PATTERNS = (
    "heldout", "held-out", "master_gold", "master.18_cases", "adjudicated_heldout",
    "review_packets", "human_reviews", "eval_gold.locked", "eval_gold_review",
    "development_heldout_split", "gold_lock_manifest", "gold_lock_audit",
    # These V3 query assets contain or expose the frozen held-out assignment even
    # though their filenames do not themselves say "heldout".  Stage 2R must
    # mine from a separately sanitized non-held-out projection instead.
    "eval_queries.candidate.jsonl", "eval_queries.locked.jsonl",
)
PRIMARY_WORKSPACE_EXCLUSIONS = frozenset({
    "secondary_reviews", "agreements", "adjudications", "existing_gold", "system_predictions",
})


class ProtectedPathError(RuntimeError):
    pass


def assert_primary_workspace_isolated(paths: list[str]) -> None:
    exposed = {part.casefold() for value in paths for part in Path(value).parts} & PRIMARY_WORKSPACE_EXCLUSIONS
    if exposed:
        raise ProtectedPathError(f"primary workspace exposes forbidden directories: {sorted(exposed)}")


@dataclass
class Stage2RAAccessGuard:
    repository_root: Path
    allowed_reads: list[str] = field(default_factory=list)
    forbidden_access_attempts: list[str] = field(default_factory=list)

    def validate(self, path: str | Path) -> Path:
        resolved = Path(path).resolve()
        normalized = resolved.as_posix().casefold()
        match = next((x for x in PROTECTED_PATTERNS if x in normalized), None)
        if match:
            self.forbidden_access_attempts.append(str(resolved))
            raise ProtectedPathError(f"Stage 2R-A protected path: {match}")
        self.allowed_reads.append(self._display(resolved))
        return resolved

    def read_text(self, path: str | Path) -> str:
        return self.validate(path).read_text(encoding="utf-8")

    def audit(self) -> dict[str, object]:
        return {"heldout_accessed": False, "forbidden_access_attempts": len(self.forbidden_access_attempts),
                "allowed_reads": sorted(set(self.allowed_reads)), "protected_patterns": list(PROTECTED_PATTERNS)}

    def _display(self, path: Path) -> str:
        try: return path.relative_to(self.repository_root.resolve()).as_posix()
        except ValueError: return str(path)
