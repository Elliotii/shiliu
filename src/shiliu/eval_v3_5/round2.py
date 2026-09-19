from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from shiliu.eval_v3_5.intake import ROUND2_ORDER, validate_human_intake
from shiliu.eval_v3_5.models import MasterCaseCandidate


ROUND2_INPUT = "round2_primary_cases_002_004_005_006_011_014_016_018.completed.jsonl"
ROUND2_INPUT_HASH = "036fad9aa0d2bc4c437fb31fbfa86ab07e1694554f804e66ba8feeab3dabf73e"
CALIBRATION_LEDGER_HASH = "06ce0e3980e09618a901f572e96ab9d0970660219f33cab79630860532f01737"
VALIDATOR_VERSION = "v3.5-round2-intake-validator-v1"


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _canonical(records: list[dict[str, object]]) -> str:
    return "".join(
        json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for item in records
    )


def _candidate_map(root: Path) -> dict[str, MasterCaseCandidate]:
    records = _jsonl(root / "master_case_candidates.jsonl") + _jsonl(root / "master_case_reserves.jsonl")
    return {item.case_id: item for item in (MasterCaseCandidate.model_validate(value) for value in records)}


def validate_round2(*, root: str | Path = "research/v3_5") -> tuple[list[dict[str, object]], dict[str, object]]:
    records, audit = validate_human_intake(
        root=root,
        intake_files=(ROUND2_INPUT,),
        expected_input_hashes={ROUND2_INPUT: ROUND2_INPUT_HASH},
        authorized_order=ROUND2_ORDER,
        expected_label_distribution={
            "sufficient": 3, "partial": 1, "insufficient": 3, "unverifiable": 1,
        },
    )
    if audit["needs_second_review_cases"] != ["CASE_004"]:
        raise ValueError(
            f"CASE_004 must be the sole second-review Case: {audit['needs_second_review_cases']}"
        )
    case004 = next(item for item in records if item["case_id"] == "CASE_004")
    if (
        case004["sufficiency_label"] != "partial"
        or case004["review_confidence"] != "medium"
        or case004["needs_second_review"] is not True
    ):
        raise ValueError("CASE_004 prior decision identity is incompatible with adjudication authorization")
    return records, audit


def write_round2_outputs(
    *, root: str | Path = "research/v3_5", validated_at: str | None = None
) -> dict[str, object]:
    root = Path(root)
    human = root / "human_reviews"
    records, audit = validate_round2(root=root)
    timestamp = validated_at or datetime.now(timezone.utc).isoformat()

    round2_path = human / "review_decisions.round2.8_cases.validated.jsonl"
    round2_text = _canonical(records)
    round2_path.write_text(round2_text, encoding="utf-8")
    round2_hash = sha256(round2_text.encode("utf-8")).hexdigest()
    audit.update({
        "validator_version": VALIDATOR_VERSION,
        "validated_at": timestamp,
        "input_sha256": ROUND2_INPUT_HASH,
        "canonical_output_path": str(round2_path),
        "canonical_output_sha256": round2_hash,
    })
    (human / "round2_8_case_validation_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    calibration_path = human / "review_decisions.calibration.10_cases.validated.jsonl"
    if sha256(calibration_path.read_bytes()).hexdigest() != CALIBRATION_LEDGER_HASH:
        raise ValueError("validated ten-case calibration ledger drift")
    calibration = _jsonl(calibration_path)
    master_records = calibration + records
    if len(master_records) != 18 or len({item["case_id"] for item in master_records}) != 18:
        raise ValueError("provisional Master ledger must contain 18 unique Cases")
    master_path = human / "review_decisions.master.18_cases.provisional.jsonl"
    master_text = _canonical(master_records)
    master_path.write_text(master_text, encoding="utf-8")
    master_hash = sha256(master_text.encode("utf-8")).hexdigest()
    labels = Counter(str(item["sufficiency_label"]) for item in master_records)
    expected_labels = Counter({"sufficient": 9, "partial": 1, "insufficient": 6, "unverifiable": 2})
    if labels != expected_labels:
        raise ValueError(f"provisional distribution mismatch: {dict(labels)}")

    cases = _candidate_map(root)
    sources = Counter(cases[str(item["case_id"])].source_type or cases[str(item["case_id"])].source_state for item in master_records)
    expected_sources = Counter({"ai": 10, "asr": 2, "human": 2, "title_only": 2, "query_corpus": 2})
    if sources != expected_sources:
        raise ValueError(f"provisional source distribution mismatch: {dict(sources)}")
    master_manifest = {
        "ledger_status": "Provisional Master Ledger",
        "gold_status": "Not Final Gold",
        "path": str(master_path),
        "sha256": master_hash,
        "record_count": 18,
        "case_ids": [item["case_id"] for item in master_records],
        "label_distribution": dict(sorted(labels.items())),
        "source_type_distribution": dict(sorted(sources.items())),
        "blocking_conditions": [
            "CASE_004 requires focused second review",
            "Development / Held-out not assigned",
            "Eval Protocol not frozen",
        ],
        "created_at": timestamp,
        "validator_version": VALIDATOR_VERSION,
    }
    (human / "review_decisions.master.18_cases.provisional.manifest.json").write_text(
        json.dumps(master_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "round2_sha256": round2_hash,
        "master_sha256": master_hash,
        "label_distribution": dict(sorted(labels.items())),
        "source_type_distribution": dict(sorted(sources.items())),
    }


if __name__ == "__main__":
    print(json.dumps(write_round2_outputs(), ensure_ascii=False, sort_keys=True))
