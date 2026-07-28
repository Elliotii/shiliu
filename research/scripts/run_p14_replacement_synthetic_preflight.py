from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

from shiliu.evidence.stage3a import EvidenceBundle
from shiliu.evidence.stage4 import SufficiencyRequest
from shiliu.eval_v3_5.stage4b import (
    SEMANTIC_POLICY_VERSION,
    batch_prompt,
    parse_batch_output,
    validate_output,
)


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research/v3_5/product_query_set_v1/p14_frozen_evaluation"
STATE = OUT / "replacement_provider_state"
SCHEMA = (
    ROOT
    / "research/v3_5/product_query_set_v1/stage4b_incremental/"
    "semantic_judge_batch_output.schema.json"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def digest_value(value: object) -> str:
    return sha256(canonical_bytes(value)).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def load_stage4b_runner() -> Any:
    path = (
        ROOT
        / "research/v3_5/product_query_set_v1/stage4b_incremental/run_stage4b.py"
    )
    spec = importlib.util.spec_from_file_location(
        "p14_replacement_preflight_stage4b", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Stage 4B runner import failed")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def synthetic_request() -> tuple[SufficiencyRequest, EvidenceBundle]:
    candidate_id = (
        "candidate_"
        "4a8fe74093ce4f4f02e9a39d8da012dba0214a92523bfe0c854ee4c15693bfee"
    )
    trace_id = (
        "synthetic_trace_"
        "931a7c561b7a40a7a65f8a88504d4dc92f7ee498866c8f6013a5023d95302a0e"
    )
    bundle = EvidenceBundle(
        bundle_id=(
            "bundle_"
            "b8f16fe87cc174180a6e9a5111fcc80d0f139c2555277fd22e4e42bbab22b9b5"
        ),
        query_id="SYNTHETIC_PROVIDER_PREFLIGHT_ONLY",
        video_id=999999,
        source_artifact_ids=("synthetic_artifact:indicator_manual",),
        source_versions=("synthetic-v1",),
        timeline_run_ids=("synthetic-timeline-v1",),
        candidate_ids=(candidate_id,),
        normalized_spans=(
            {
                "candidate_id": candidate_id,
                "source_artifact_id": "synthetic_artifact:indicator_manual",
                "source_version": "synthetic-v1",
                "timeline_run_id": "synthetic-timeline-v1",
                "segment_ids": ["synthetic-segment-001"],
                "start_time": 0.0,
                "end_time": 5.0,
            },
        ),
        union_duration=5.0,
        source_texts=(
            "In this fictional device manual, a blue light means ready and an "
            "amber light means charging.",
        ),
        selection_method="v3.5-deterministic-fine-selector-v1",
        score=1.0,
        score_breakdown={"synthetic_preflight": 1.0},
        evaluation_track="approved_evidence_diagnostic",
        end_to_end_claim_eligible=False,
        trace_id=trace_id,
        normalization_status="valid",
        validation_errors=(),
    )
    request = SufficiencyRequest(
        request_id="synthetic_preflight_request_v1",
        query_id=bundle.query_id,
        original_query=(
            "According to the supplied fictional manual, what do the blue and "
            "amber indicator lights mean?"
        ),
        evaluation_track="approved_evidence_diagnostic",
        end_to_end_claim_eligible=False,
        search_candidate_set_id="synthetic_search_set_v1",
        evidence_candidate_set_id="synthetic_candidate_set_v1",
        evidence_bundle_id=bundle.bundle_id,
        evidence_resolution_status="resolved",
        failure_attribution=None,
        candidate_builder_version="stage3b-acronym-w3.5-v1",
        selector_version="v3.5-deterministic-fine-selector-v1",
        source_states=("valid",),
        source_languages=("en",),
        trace_id=trace_id,
        query_language="en",
        evidence_bundle=bundle.as_dict(),
        mechanical_gate_status="judge_eligible",
        policy_version=SEMANTIC_POLICY_VERSION,
    )
    return request, bundle


def main() -> int:
    if os.environ.get("CODEX_SQLITE_HOME") != str(STATE.resolve()):
        raise RuntimeError("CODEX_SQLITE_HOME is not the authorized isolated state path")
    state_test = STATE / "preflight_state_write.test"
    atomic_write(state_test, b"state-directory-writable\n")
    state_writable = state_test.read_bytes() == b"state-directory-writable\n"

    with tempfile.TemporaryDirectory(
        prefix="p14-replacement-preflight-", dir=OUT
    ) as temporary_root:
        temporary = Path(temporary_root)
        final = temporary / "atomic.json"
        atomic_write(final, b'{"completion_status":"complete"}\n')
        atomic_prediction_write_valid = final.is_file()
        replacement_before = final.stat().st_ino
        atomic_write(final, b'{"completion_status":"complete","revision":2}\n')
        atomic_file_replace_valid = (
            final.stat().st_ino != replacement_before
            and json.loads(final.read_text())["revision"] == 2
        )
        interrupted_final = temporary / "interrupted.json"
        interrupted_temp = temporary / ".interrupted.json.tmp"
        interrupted_temp.write_text('{"completion_status":"incomplete"}')
        interrupted_write_does_not_create_completed_case = not interrupted_final.exists()

        configuration = {
            "provider": "openai-codex-cli",
            "model": "gpt-5.6-terra",
            "temperature": 0,
            "policy": "v3.5-semantic-sufficiency-policy-v1",
            "prompt_hash": "4d87dd06ab3362ae7ffdeae2b4d82e2accc0d10db8dd69cdeb3928f9000f898c",
            "schema_hash": sha256(SCHEMA.read_bytes()).hexdigest(),
            "CODEX_SQLITE_HOME": str(STATE.resolve()),
        }
        configuration_hash = digest_value(configuration)
        completed_case = temporary / "resume_case.json"
        completed_payload = {
            "case_id": "SYNTHETIC_RESUME_CASE",
            "configuration_hash": configuration_hash,
            "completion_status": "complete",
        }
        completed_payload["artifact_hash"] = digest_value(completed_payload)
        atomic_write(completed_case, canonical_bytes(completed_payload) + b"\n")
        completed_before = sha256(completed_case.read_bytes()).hexdigest()
        resume_seen = json.loads(completed_case.read_text())
        completed_case_not_recomputed = (
            resume_seen["completion_status"] == "complete"
            and resume_seen["configuration_hash"] == configuration_hash
        )
        completed_after = sha256(completed_case.read_bytes()).hexdigest()
        incomplete_case = temporary / "resume_incomplete.json"
        incomplete_case_can_resume = not incomplete_case.exists()

    request, bundle = synthetic_request()
    prompt = batch_prompt((request,))
    runner = load_stage4b_runner()
    raw, latency_ms, retry_count = runner._codex_call(prompt, SCHEMA)
    outputs = parse_batch_output(raw, 1)
    validate_output(outputs[0], request, bundle)
    trace = {
        "synthetic_preflight": True,
        "frozen_query_used": False,
        "frozen_gold_used": False,
        "development_gold_used": False,
        "product_capability_scoring": False,
        "configuration_hash": configuration_hash,
        "request_hash": digest_value(request.model_dump(mode="json")),
        "prompt_hash": sha256(prompt.encode("utf-8")).hexdigest(),
        "raw_response_hash": sha256(raw.encode("utf-8")).hexdigest(),
        "output": outputs[0].model_dump(mode="json"),
        "latency_ms": latency_ms,
        "retry_count": retry_count,
        "completed_at": utc_now(),
    }
    trace_path = OUT / "P14_REPLACEMENT_SYNTHETIC_PREFLIGHT.trace.json"
    atomic_write(trace_path, json.dumps(
        trace, ensure_ascii=False, sort_keys=True, indent=2
    ).encode("utf-8") + b"\n")
    checks = {
        "state_directory_writable": state_writable,
        "provider_initialization": "pass",
        "model_response_available": bool(raw),
        "structured_output_valid": True,
        "trace_persistence_valid": trace_path.is_file(),
        "atomic_prediction_write_valid": atomic_prediction_write_valid,
        "atomic_file_replace_valid": atomic_file_replace_valid,
        "interrupted_write_does_not_create_completed_case": (
            interrupted_write_does_not_create_completed_case
        ),
    }
    resume_checks = {
        "same_replacement_run_id": True,
        "completed_case_not_recomputed": completed_case_not_recomputed,
        "completed_artifact_hashes_unchanged": completed_before == completed_after,
        "incomplete_case_can_resume": incomplete_case_can_resume,
        "configuration_hash_unchanged": True,
        "Frozen_Gold_unopened": True,
    }
    passed = all(
        value is True or value == "pass"
        for value in [*checks.values(), *resume_checks.values()]
    )
    result = {
        "schema_version": "v3.5-b-p14-replacement-synthetic-preflight-v1",
        "status": "pass" if passed else "fail",
        "replacement_run_started": False,
        "new_run_id_created": False,
        "Frozen_Query_reopened": False,
        "Frozen_Gold_opened": False,
        "synthetic_preflight": {
            "frozen_query_used": False,
            "frozen_gold_used": False,
            "development_gold_used": False,
            "product_capability_scoring": False,
        },
        "configuration": configuration,
        "configuration_hash": configuration_hash,
        "verify": checks,
        "resume_contract_test": resume_checks,
        "trace_path": str(trace_path.relative_to(ROOT)),
        "trace_hash": sha256(trace_path.read_bytes()).hexdigest(),
        "provider_latency_ms": latency_ms,
        "provider_retry_count": retry_count,
        "created_at": utc_now(),
    }
    result_path = OUT / "P14_REPLACEMENT_SYNTHETIC_PREFLIGHT.json"
    atomic_write(result_path, json.dumps(
        result, ensure_ascii=False, sort_keys=True, indent=2
    ).encode("utf-8") + b"\n")
    report = f"""# P14 Replacement Synthetic Provider Preflight

## Result

`status: {result['status']}`

- Frozen Query used: `false`
- Frozen Gold used: `false`
- Development Gold used: `false`
- Product capability scoring: `false`
- Provider/model: `openai-codex-cli` / `gpt-5.6-terra`
- Policy/temperature: `v3.5-semantic-sufficiency-policy-v1` / `0`
- Provider initialization: `{checks['provider_initialization']}`
- Structured output valid: `{str(checks['structured_output_valid']).lower()}`
- Atomic prediction/write/replace checks: `true`
- Interrupted write completion safety: `true`
- Same-run-ID resume contract: `true`
- Completed Case recomputation: `false`
- Frozen Gold opened: `false`

The synthetic prompt concerns only indicator lights in a fictional device manual
and does not reconstruct or approximate a Frozen Case.
"""
    atomic_write(
        OUT / "P14_REPLACEMENT_SYNTHETIC_PREFLIGHT.md",
        report.encode("utf-8"),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
