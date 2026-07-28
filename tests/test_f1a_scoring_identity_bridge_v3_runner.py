from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / (
    "research/v3_5/product_query_set_v1/f1a_candidate_builder_major_cycle_1/"
    "run_f1a_scoring_identity_bridge_v3.py"
)
SPEC = importlib.util.spec_from_file_location("f1a_scorer_v3_runner", RUNNER_PATH)
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


def test_runner_uses_frozen_snapshot_as_authoritative_mapping() -> None:
    mapping = RUNNER.canonicalizer()
    assert len(mapping) == 144
    assert mapping.source_sha256 == RUNNER.EXPECTED_MAPPING_SOURCE_SHA256


def test_runner_declares_generic_scorer_and_no_query_rules() -> None:
    assert RUNNER.SCORER_VERSION == "scorer_v3_video_identity_canonicalization"
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert '"query_specific_rules": 0' in source


def test_runner_enforces_single_formal_run_order() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "Development Eval v3 already exists" in source
    assert "Stress Eval v3 already exists" in source
    assert "requires exactly one completed Development Eval v3" in source


def test_preflight_does_not_open_development_gold_or_replay_candidates() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")
    preflight_source = source[source.index("def preflight"):source.index("def _invalid_identity_count")]
    assert "gold_hashes()" not in preflight_source
    assert "candidate_runtime" not in preflight_source
    assert '"development_gold_opened": False' in preflight_source
    assert '"candidate_replay_started": False' in preflight_source
