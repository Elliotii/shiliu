from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from shiliu.eval_v3_5.models import ActiveCalibrationRecord, MasterCaseCandidate, ReviewDecisionTemplate


AUTHORIZED_ORDER = (
    "CASE_015",
    "CASE_017",
    "CASE_013",
    "CASE_001",
    "CASE_003",
    "CASE_012",
)
ORIGINAL_DECISION_TEMPLATE_SHA256 = "8580ce39cb93989dc4dec21ea0c213ae0a5367820e5c061ff568a6cd5b3f88ee"
NEW_UNVERIFIABLE_RESERVES = {
    "RESERVE_007": ("Q02", 142, "BV1zjNG6mEPi"),
    "RESERVE_008": ("Q22", 143, "BV1wtEt6YEiC"),
}


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def validate_calibration_assets(
    *,
    root: str | Path = "research/v3_5",
    protocol_path: str | Path = "V3_5_EVAL_PROTOCOL_DRAFT.md",
    snapshot_db: str | Path = "/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/shiliu_eval.db",
    gold_path: str | Path = "research/v3_eval/eval_gold.locked.jsonl",
    artifact_manifest_path: str | Path = "research/v3_eval/artifact_manifest.jsonl",
) -> dict[str, int]:
    root = Path(root)
    active = [
        ActiveCalibrationRecord.model_validate(item)
        for item in _jsonl(root / "active_review_calibration.jsonl")
    ]
    if tuple(item.case_id for item in active) != AUTHORIZED_ORDER:
        raise ValueError("active calibration must contain the six authorized cases in order")
    if [item.review_order for item in active] != list(range(1, 7)):
        raise ValueError("calibration review_order must be contiguous from 1 to 6")
    for item in active:
        if item.decision_record_id != f"CAL_DECISION_{item.case_id}":
            raise ValueError(f"invalid calibration decision record ID: {item.case_id}")
        if not Path(item.packet_path).is_file():
            raise ValueError(f"missing calibration packet: {item.case_id}")

    decisions = [
        ReviewDecisionTemplate.model_validate(item)
        for item in _jsonl(root / "review_decisions.calibration.template.jsonl")
    ]
    if tuple(item.case_id for item in decisions) != AUTHORIZED_ORDER:
        raise ValueError("calibration decisions must match authorized order")
    original_template = root / "review_decisions.template.jsonl"
    if sha256(original_template.read_bytes()).hexdigest() != ORIGINAL_DECISION_TEMPLATE_SHA256:
        raise ValueError("original 26-record decision template changed")

    reserves = [
        MasterCaseCandidate.model_validate(item)
        for item in _jsonl(root / "master_case_reserves.jsonl")
    ]
    if {item.case_id for item in reserves} & set(AUTHORIZED_ORDER):
        raise ValueError("reserve candidate appears in active calibration")
    if len(reserves) != 8:
        raise ValueError("follow-up reserve manifest must contain eight inactive candidates")

    manifest = json.loads((root / "review_packet_manifest.json").read_text(encoding="utf-8"))
    entries = {item["case_id"]: item for item in manifest["packets"]}
    for case_id in AUTHORIZED_ORDER:
        if case_id not in entries:
            raise ValueError(f"active packet missing from packet manifest: {case_id}")
    for case_id in NEW_UNVERIFIABLE_RESERVES:
        if case_id not in entries:
            raise ValueError(f"new reserve packet missing from packet manifest: {case_id}")
        packet_path = Path(entries[case_id]["packet_path"])
        if sha256(packet_path.read_bytes()).hexdigest() != entries[case_id]["sha256"]:
            raise ValueError(f"new reserve packet hash mismatch: {case_id}")

    gold = {item["query_id"]: item for item in _jsonl(Path(gold_path))}
    artifacts = _jsonl(Path(artifact_manifest_path))
    connection = sqlite3.connect(f"file:{Path(snapshot_db).resolve()}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        for case_id, (query_id, video_id, bvid) in NEW_UNVERIFIABLE_RESERVES.items():
            case = next(item for item in reserves if item.case_id == case_id)
            if case.target_video_id != video_id or case.target_bvid != bvid:
                raise ValueError(f"new reserve identity mismatch: {case_id}")
            if video_id not in gold[query_id]["title_only_relevant_ids"]:
                raise ValueError(f"new reserve lacks frozen U_title provenance: {case_id}")
            if video_id in {49, 125, 137} or case.source_state != "subtitle_missing":
                raise ValueError(f"new reserve is not an independent missing-source case: {case_id}")
            row = connection.execute(
                "SELECT status,error_code,raw_subtitle_path FROM videos WHERE id=?", (video_id,)
            ).fetchone()
            if row is None or row["status"] != "skipped_no_subtitle" or row["error_code"] != "no_supported_subtitle" or row["raw_subtitle_path"]:
                raise ValueError(f"new reserve source state is not frozen/real: {case_id}")
            raw_records = [
                item for item in artifacts
                if item["video_id"] == video_id and item["artifact_type"] == "raw_subtitle"
            ]
            if len(raw_records) != 1 or raw_records[0]["status"] != "not_declared":
                raise ValueError(f"new reserve raw artifact provenance mismatch: {case_id}")
    finally:
        connection.close()

    protocol = Path(protocol_path).read_text(encoding="utf-8")
    required_protocol_text = (
        "Full Transcript Accessible ≠ Full Transcript Linearly Read From Start to End",
        "not exhaustive proofs",
        "English-source positive evidence: not established",
        "Cross-language evidence resolution: not evaluated",
        "Reserve candidates are inactive by default",
        "Round 1: 6-case Label Calibration",
        "Round 2: Remaining necessary Primary Cases",
        "Round 3: Targeted Reserve Activation only when required",
    )
    for phrase in required_protocol_text:
        if phrase not in protocol:
            raise ValueError(f"required protocol correction missing: {phrase}")

    return {
        "active_cases": len(active),
        "blank_calibration_decisions": len(decisions),
        "inactive_reserves": len(reserves),
        "new_unverifiable_reserves": len(NEW_UNVERIFIABLE_RESERVES),
    }
