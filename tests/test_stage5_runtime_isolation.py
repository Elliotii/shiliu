from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from shiliu.app import Application
from shiliu.eval_v3_5.frozen_auto_smoke import (
    FrozenAutoSmokeBlocked,
    run_frozen_auto_smoke,
)
from shiliu.eval_v3_5.runtime_guard import (
    FrozenEvalRuntimeConfig,
    FrozenEvalRuntimeGuardError,
    SealedRuntimeArtifact,
    preflight_frozen_eval_runtime,
)


def _artifact(path: Path, content: bytes) -> SealedRuntimeArtifact:
    path.write_bytes(content)
    return SealedRuntimeArtifact(path=path, sha256=sha256(content).hexdigest())


def _config(tmp_path: Path, **overrides) -> FrozenEvalRuntimeConfig:
    values = {
        "runtime_mode": "frozen_eval_runtime",
        "corpus_identity": "sealed-fixture-v1",
        "sealed_corpus_identity": "sealed-fixture-v1",
        "sync_allowed": False,
        "mutable_index_allowed": False,
        "database": _artifact(tmp_path / "fixture.db", b"sealed database"),
        "lexical_index": _artifact(
            tmp_path / "lexical.index", b"sealed lexical"
        ),
        "dense_index": _artifact(tmp_path / "dense.index", b"sealed dense"),
    }
    values.update(overrides)
    return FrozenEvalRuntimeConfig(**values)


def test_product_runtime_is_explicitly_live_mutable_and_syncable(
    app_paths,
) -> None:
    application = Application(app_paths)
    runtime = application.runtime_config
    assert runtime.runtime_mode == "product_runtime"
    assert runtime.corpus_identity == "shiliu-live-current"
    assert runtime.sync_allowed is True
    assert runtime.mutable_index_allowed is True
    assert (
        application.stage5_pipeline.evidence_search.runtime_corpus_identity
        == "shiliu-live-current"
    )


def test_frozen_eval_guard_rejects_live_current(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        corpus_identity="shiliu-live-current",
        sealed_corpus_identity="shiliu-live-current",
    )
    with pytest.raises(
        FrozenEvalRuntimeGuardError, match="mutable product corpus"
    ) as error:
        preflight_frozen_eval_runtime(config)
    assert error.value.code == "live_current_runtime_rejected"


def test_frozen_eval_guard_rejects_missing_or_mismatched_hash(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    config.database.path.unlink()
    with pytest.raises(FrozenEvalRuntimeGuardError) as missing:
        preflight_frozen_eval_runtime(config)
    assert missing.value.code == "sealed_artifact_missing"

    config = _config(tmp_path)
    config.dense_index.path.write_bytes(b"mutated")
    with pytest.raises(FrozenEvalRuntimeGuardError) as mismatch:
        preflight_frozen_eval_runtime(config)
    assert mismatch.value.code == "dense_index_hash_mismatch"


def test_frozen_eval_seal_requires_all_hashes_and_disables_sync(
    tmp_path: Path,
) -> None:
    incomplete = {
        "runtime_mode": "frozen_eval_runtime",
        "corpus_identity": "sealed-fixture-v1",
        "sealed_corpus_identity": "sealed-fixture-v1",
        "sync_allowed": False,
        "mutable_index_allowed": False,
        "artifacts": {},
    }
    with pytest.raises(FrozenEvalRuntimeGuardError) as missing:
        FrozenEvalRuntimeConfig.from_dict(incomplete, base_dir=tmp_path)
    assert missing.value.code == "missing_artifact_hashes"

    with pytest.raises(FrozenEvalRuntimeGuardError) as sync:
        preflight_frozen_eval_runtime(_config(tmp_path, sync_allowed=True))
    assert sync.value.code == "sync_must_be_disabled"


def test_sealed_fixture_preflight_passes_without_eval_content(
    tmp_path: Path,
) -> None:
    result = preflight_frozen_eval_runtime(_config(tmp_path))
    assert result["preflight_status"] == "pass"
    assert result["sync_allowed"] is False
    assert set(result["verified_hashes"]) == {
        "database",
        "lexical_index",
        "dense_index",
    }


def test_frozen_runner_rejects_missing_guard_before_loading_inputs(
    tmp_path: Path, monkeypatch
) -> None:
    def forbidden_load(_root):
        raise AssertionError("frozen inputs must not be loaded before guard")

    monkeypatch.setattr(
        "shiliu.eval_v3_5.frozen_auto_smoke.load_frozen_inputs",
        forbidden_load,
    )
    with pytest.raises(FrozenAutoSmokeBlocked) as error:
        run_frozen_auto_smoke(
            repository_root=tmp_path,
            snapshot_db=tmp_path / "snapshot.db",
            snapshot_artifacts=tmp_path / "artifacts",
            artifact_manifest=tmp_path / "manifest.jsonl",
        )
    assert error.value.code == "frozen_eval_runtime_guard_missing"
