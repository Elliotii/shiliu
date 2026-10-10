from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_v4_1_continuation as continuation


def _identity(spec: continuation.PhaseSpec, marker: str = "a") -> dict[str, object]:
    return {
        "checkpoint_version": continuation.CHECKPOINT_VERSION,
        "phase_id": spec.phase_id,
        "mode": spec.mode,
        "code_state": spec.code_state,
        "case_ids": list(spec.case_ids),
        "query_hashes": {value: marker for value in spec.case_ids},
        "manifest_sha256": marker,
        "corpus_sha256": marker,
        "source_code_sha256": marker,
        "provider_identity": {"configuration": "baseline_only"},
        "logical_cap": spec.logical_cap,
        "http_cap": spec.http_cap,
        "identity_sha256": marker,
    }


def _response(case_id: str, mode: str = "fast") -> Any:
    return SimpleNamespace(
        model_dump=lambda **_kwargs: {"private": f"answer-{case_id}"},
    )


def _run(case_id: str, *, failed: bool = False) -> continuation.EphemeralRun:
    return continuation.EphemeralRun(
        case_id=case_id,
        public_measurement={
            "case_id": case_id,
            "mode": "fast",
            "provider_failed": failed,
            "logical_provider_invocations": 2,
            "transport_http_attempts": 2,
        },
        response=_response(case_id),
        full_current_evidence=(
            {"citation_id": "c1", "quote_text": "verbatim-secret-evidence"},
        ),
        private_strings=(
            f"query-{case_id}",
            f"answer-{case_id}",
            "verbatim-secret-evidence",
        ),
    )


def _scores() -> dict[str, str]:
    return {
        "supportedness": "pass",
        "usefulness": "pass",
        "coverage": "pass",
        "status_honesty": "pass",
        "reason": "bounded assessment",
    }


@pytest.fixture
def isolated_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, continuation.PhaseSpec]:
    phases: dict[str, continuation.PhaseSpec] = {}
    for name, source in continuation.PHASES.items():
        phases[name] = continuation.PhaseSpec(
            source.phase_id,
            source.mode,
            source.code_state,
            source.case_ids,
            source.logical_cap,
            source.http_cap,
            source.logical_reservation_per_run,
            source.http_reservation_per_run,
            source.paired_before,
        )
    monkeypatch.setattr(continuation, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(continuation, "PHASES", phases)
    return phases


def test_checkpoint_is_atomic_private_bounded_and_mode_0600(
    isolated_paths: dict[str, continuation.PhaseSpec],
) -> None:
    spec = isolated_paths["fast_before"]
    store = continuation.E2ECheckpointStore(
        spec, _identity(spec), private_strings=("secret-query",)
    )
    store.begin(spec.case_ids[0])
    value = json.loads(spec.checkpoint_path.read_text(encoding="utf-8"))
    assert value["runs"][spec.case_ids[0]]["state"] == "in_flight"
    assert "secret-query" not in spec.checkpoint_path.read_text(encoding="utf-8")
    assert os.stat(spec.checkpoint_path).st_mode & 0o777 == 0o600


def test_provider_return_before_checkpoint_leaves_unknown_in_flight_and_blocks(
    isolated_paths: dict[str, continuation.PhaseSpec],
) -> None:
    spec = isolated_paths["fast_before"]
    store = continuation.E2ECheckpointStore(
        spec, _identity(spec), private_strings=()
    )
    store.begin(spec.case_ids[0])
    with pytest.raises(continuation.E2ERecoveryBlocked, match="unknown"):
        continuation.E2ECheckpointStore(
            spec, _identity(spec), private_strings=()
        )


@pytest.mark.parametrize(
    "state",
    ("provider_complete_pending_review", "review_in_progress"),
)
def test_provider_after_checkpoint_or_review_crash_blocks_without_replay(
    isolated_paths: dict[str, continuation.PhaseSpec],
    state: str,
) -> None:
    spec = isolated_paths["fast_before"]
    store = continuation.E2ECheckpointStore(
        spec, _identity(spec), private_strings=()
    )
    result = _run(spec.case_ids[0])
    store.begin(result.case_id)
    store.checkpoint_provider_result(result)
    if state == "review_in_progress":
        store.begin_review(result)
    with pytest.raises(continuation.E2ERecoveryBlocked, match="unknown"):
        continuation.E2ECheckpointStore(
            spec, _identity(spec), private_strings=()
        )


def test_completed_run_is_not_reopened_or_duplicated(
    isolated_paths: dict[str, continuation.PhaseSpec],
) -> None:
    spec = isolated_paths["fast_before"]
    store = continuation.E2ECheckpointStore(
        spec, _identity(spec), private_strings=()
    )
    result = _run(spec.case_ids[0])
    store.begin(result.case_id)
    store.checkpoint_provider_result(result)
    store.begin_review(result)
    store.finish_review(result, _scores())
    before = spec.checkpoint_path.read_bytes()
    store.begin(result.case_id)
    assert spec.checkpoint_path.read_bytes() == before
    assert store.run(result.case_id)["state"] == "review_complete"


def test_campaign_identity_mismatch_blocks(
    isolated_paths: dict[str, continuation.PhaseSpec],
) -> None:
    spec = isolated_paths["fast_before"]
    continuation.E2ECheckpointStore(
        spec, _identity(spec, "a"), private_strings=()
    )
    with pytest.raises(continuation.E2ERecoveryBlocked, match="identity mismatch"):
        continuation.E2ECheckpointStore(
            spec, _identity(spec, "b"), private_strings=()
        )


def test_private_answer_evidence_and_reason_are_not_persisted(
    isolated_paths: dict[str, continuation.PhaseSpec],
) -> None:
    spec = isolated_paths["fast_before"]
    store = continuation.E2ECheckpointStore(
        spec, _identity(spec), private_strings=()
    )
    result = _run(spec.case_ids[0])
    store.begin(result.case_id)
    store.checkpoint_provider_result(result)
    store.begin_review(result)
    review = _scores()
    review["reason"] = "answer-" + result.case_id
    store.finish_review(result, review)
    text = spec.checkpoint_path.read_text(encoding="utf-8")
    assert f"answer-{result.case_id}" not in text
    assert "query-" not in text
    assert '"quote_text"' not in text
    assert "reason_redacted_private_overlap" in text


def test_two_consecutive_provider_failures_fail_fast(
    isolated_paths: dict[str, continuation.PhaseSpec],
) -> None:
    spec = isolated_paths["fast_before"]
    store = continuation.E2ECheckpointStore(
        spec, _identity(spec), private_strings=()
    )
    for case_id in spec.case_ids[:2]:
        result = _run(case_id, failed=True)
        store.begin(case_id)
        store.checkpoint_provider_result(result)
        store.begin_review(result)
        store.finish_review(result, _scores())
    store.finish_phase()
    assert store.data["state"] == "blocked"
    assert store.data["completed_run_count"] == 2
    assert store.run(spec.case_ids[2])["state"] == "pending"


def test_caps_reserve_worst_case_before_provider(
    isolated_paths: dict[str, continuation.PhaseSpec],
) -> None:
    spec = isolated_paths["fast_before"]
    store = continuation.E2ECheckpointStore(
        spec, _identity(spec), private_strings=()
    )
    store.data["logical_provider_invocations"] = spec.logical_cap - 2
    store._write()
    with pytest.raises(continuation.E2ERecoveryBlocked, match="phase call cap"):
        store.begin(spec.case_ids[0])


def test_provider_counting_matches_fast_and_deep_trace_shapes() -> None:
    assert continuation._provider_counts(
        "fast",
        {
            "query_analysis_retry_count": 1,
            "answer_provider_call_count": 2,
            "transport_retry_count": 1,
        },
    ) == (3, 5)
    assert continuation._provider_counts(
        "deep",
        {
            "decision_rounds": 3,
            "events": [
                {"event_type": "decision", "retry_count": 1},
                {"event_type": "guard", "retry_count": 9},
            ],
            "finalization": {
                "answer_provider_call_count": 1,
                "transport_retry_count": 1,
            },
        },
    ) == (4, 6)
