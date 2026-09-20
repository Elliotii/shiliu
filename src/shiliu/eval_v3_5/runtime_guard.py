from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping


FROZEN_EVAL_RUNTIME_MODE = "frozen_eval_runtime"
LIVE_CURRENT_CORPUS_IDENTITY = "shiliu-live-current"
FROZEN_EVAL_RUNTIME_GUARD_VERSION = "v3.5-frozen-eval-runtime-guard-v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class FrozenEvalRuntimeGuardError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SealedRuntimeArtifact:
    path: Path
    sha256: str


@dataclass(frozen=True)
class FrozenEvalRuntimeConfig:
    runtime_mode: str
    corpus_identity: str
    sealed_corpus_identity: str
    sync_allowed: bool
    mutable_index_allowed: bool
    database: SealedRuntimeArtifact
    lexical_index: SealedRuntimeArtifact
    dense_index: SealedRuntimeArtifact
    seal_path: Path | None = None

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
        *,
        base_dir: Path,
        seal_path: Path | None = None,
    ) -> "FrozenEvalRuntimeConfig":
        artifacts = value.get("artifacts")
        if not isinstance(artifacts, Mapping):
            raise FrozenEvalRuntimeGuardError(
                "missing_artifact_hashes",
                "Frozen Eval runtime seal must define database, lexical, and dense artifacts",
            )
        if not isinstance(value.get("sync_allowed"), bool) or not isinstance(
            value.get("mutable_index_allowed"), bool
        ):
            raise FrozenEvalRuntimeGuardError(
                "runtime_seal_invalid",
                "sync_allowed and mutable_index_allowed must be explicit booleans",
            )

        def artifact(name: str) -> SealedRuntimeArtifact:
            raw = artifacts.get(name)
            if not isinstance(raw, Mapping):
                raise FrozenEvalRuntimeGuardError(
                    "missing_artifact_hashes",
                    f"Frozen Eval runtime seal is missing {name}",
                )
            path_value = raw.get("path")
            digest = str(raw.get("sha256") or "")
            if not path_value or not _SHA256.fullmatch(digest):
                raise FrozenEvalRuntimeGuardError(
                    "missing_artifact_hashes",
                    f"Frozen Eval runtime seal has an invalid {name} path or SHA-256",
                )
            path = Path(str(path_value)).expanduser()
            if not path.is_absolute():
                path = base_dir / path
            return SealedRuntimeArtifact(path=path.resolve(), sha256=digest)

        return cls(
            runtime_mode=str(value.get("runtime_mode") or ""),
            corpus_identity=str(value.get("corpus_identity") or ""),
            sealed_corpus_identity=str(value.get("sealed_corpus_identity") or ""),
            sync_allowed=value["sync_allowed"],
            mutable_index_allowed=value["mutable_index_allowed"],
            database=artifact("database"),
            lexical_index=artifact("lexical_index"),
            dense_index=artifact("dense_index"),
            seal_path=seal_path,
        )


def load_frozen_eval_runtime_config(path: Path) -> FrozenEvalRuntimeConfig:
    resolved = path.expanduser().resolve()
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FrozenEvalRuntimeGuardError(
            "runtime_seal_unreadable",
            f"Frozen Eval runtime seal cannot be read: {type(exc).__name__}",
        ) from exc
    if not isinstance(value, Mapping):
        raise FrozenEvalRuntimeGuardError(
            "runtime_seal_invalid", "Frozen Eval runtime seal must be a JSON object"
        )
    return FrozenEvalRuntimeConfig.from_dict(
        value,
        base_dir=resolved.parent,
        seal_path=resolved,
    )


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def preflight_frozen_eval_runtime(
    config: FrozenEvalRuntimeConfig,
) -> dict[str, object]:
    if config.runtime_mode != FROZEN_EVAL_RUNTIME_MODE:
        raise FrozenEvalRuntimeGuardError(
            "runtime_mode_not_frozen_eval",
            "Frozen Eval requires runtime_mode=frozen_eval_runtime",
        )
    if config.corpus_identity == LIVE_CURRENT_CORPUS_IDENTITY:
        raise FrozenEvalRuntimeGuardError(
            "live_current_runtime_rejected",
            "The mutable product corpus cannot be used for Frozen Eval",
        )
    if (
        not config.corpus_identity
        or config.corpus_identity != config.sealed_corpus_identity
    ):
        raise FrozenEvalRuntimeGuardError(
            "corpus_identity_mismatch",
            "Frozen Eval corpus identity does not match its seal",
        )
    if config.sync_allowed:
        raise FrozenEvalRuntimeGuardError(
            "sync_must_be_disabled",
            "Sync must be disabled in Frozen Eval runtime",
        )
    if config.mutable_index_allowed:
        raise FrozenEvalRuntimeGuardError(
            "mutable_index_rejected",
            "Mutable indexes are not allowed in Frozen Eval runtime",
        )

    verified: dict[str, str] = {}
    for name, artifact in (
        ("database", config.database),
        ("lexical_index", config.lexical_index),
        ("dense_index", config.dense_index),
    ):
        if not artifact.path.is_file():
            raise FrozenEvalRuntimeGuardError(
                "sealed_artifact_missing",
                f"Frozen Eval sealed {name} artifact is missing",
            )
        actual = sha256_file(artifact.path)
        if actual != artifact.sha256:
            raise FrozenEvalRuntimeGuardError(
                f"{name}_hash_mismatch",
                f"Frozen Eval {name} SHA-256 does not match its seal",
            )
        verified[name] = actual

    return {
        "guard_version": FROZEN_EVAL_RUNTIME_GUARD_VERSION,
        "runtime_mode": config.runtime_mode,
        "corpus_identity": config.corpus_identity,
        "sync_allowed": False,
        "mutable_index_allowed": False,
        "verified_hashes": verified,
        "preflight_status": "pass",
    }
