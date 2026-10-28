"""W00 formal maintenance roots use injected PG, never old file paths."""

import importlib.util
from pathlib import Path
import pytest
from shiliu.artifacts import ArtifactStore
from shiliu.domain import FavoriteItem


def load(name):
    import sys

    path = Path(__file__).resolve().parents[2] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_onboarding_readonly_metrics_and_gates_on_actual_pg(collection_db, tmp_path):
    module = load("run_post_v5_onboarding")
    sid = collection_db.create_favorite_source(folder_id=123, folder_title="synthetic")
    collection_db.record_source_snapshot(
        sid,
        [FavoriteItem(bvid="BV1234567890", title="synthetic", favorite_time=100)],
        processing_profile="formal",
    )
    settings = module.RunnerSettings(
        base_url="http://127.0.0.1:1",
        state_file=tmp_path / "state.json",
        poll_seconds=1,
        retry_seconds=1,
        max_discovery_attempts=1,
    )
    runner = module.OnboardingRunner(
        settings, "https://synthetic.invalid/?fid=123", db=collection_db
    )
    assert runner._source_by_folder(123)["id"] == sid
    assert runner._source(sid)["folder_id"] == 123
    gate = runner._phase_gate(sid)
    assert gate["integrity"] == "ok" and gate["imported"] == 1 and gate["pending"] == 1
    assert gate["retrieval_units"] == gate["fts_units"] == 0


@pytest.mark.parametrize(
    "module,function",
    [
        ("correct_ud_saved_page", "correct"),
        ("repair_ud_pages", "repair"),
        ("repair_ud_pages", "maintain"),
    ],
)
def test_page_repair_refuses_missing_expected_page_on_pg(
    collection_db, tmp_path, module, function
):
    # No real IDs/pages or material are loaded; the retained version/identity
    # gate must fail before any repair, without initializing a legacy DB.
    entry = load(module)
    with pytest.raises(KeyError):
        getattr(entry, function)(
            collection_db, ArtifactStore(tmp_path / "repair", collection_db)
        )
